from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class EventRequestStatus(str, Enum):
    """The full status set is the team's agreed design (backlog C-2, not yet
    built here) — see spm-brain/backlog/user-stories.md. Draft → Submitted and
    Submitted → Under Review are implemented so far; the rest are added
    so a row in any of these states can still be read back (EventRequestResponse
    would otherwise fail to validate it) and so terminal-status checks
    elsewhere (e.g. coordinator assignment) have real values to check against.
    """

    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    CHANGES_REQUESTED = "Changes Requested"
    APPROVED = "Approved"
    PLANNING = "Planning"
    SAFETY_REVIEW = "Safety Review"
    CONFIRMED = "Confirmed"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"


class EventRequestFields(BaseModel):
    """Fields that may be recorded while an event request is a draft."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_name: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=1_000)
    description: str | None = Field(default=None, max_length=5_000)
    proposed_date_times: list[AwareDatetime] = Field(default_factory=list)
    expected_attendance: int | None = Field(default=None, gt=0)
    venue_requirements: str | None = Field(default=None, max_length=2_000)
    accessibility_needs: str | None = Field(default=None, max_length=2_000)
    equipment_requirements: str | None = Field(default=None, max_length=2_000)
    registration_needs: str | None = Field(default=None, max_length=2_000)

    @field_validator(
        "event_name",
        "purpose",
        "description",
        "venue_requirements",
        "accessibility_needs",
        "equipment_requirements",
        "registration_needs",
        mode="before",
    )
    @classmethod
    def blank_text_is_missing(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class EventRequestCreate(EventRequestFields):
    pass


class EventRequestUpdate(BaseModel):
    """Editable draft fields; omitted values remain unchanged."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_name: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=1_000)
    description: str | None = Field(default=None, max_length=5_000)
    proposed_date_times: list[AwareDatetime] | None = None
    expected_attendance: int | None = Field(default=None, gt=0)
    venue_requirements: str | None = Field(default=None, max_length=2_000)
    accessibility_needs: str | None = Field(default=None, max_length=2_000)
    equipment_requirements: str | None = Field(default=None, max_length=2_000)
    registration_needs: str | None = Field(default=None, max_length=2_000)

    @field_validator(
        "event_name",
        "purpose",
        "description",
        "venue_requirements",
        "accessibility_needs",
        "equipment_requirements",
        "registration_needs",
        mode="before",
    )
    @classmethod
    def blank_text_is_missing(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class EventRequestSubmission(BaseModel):
    """Complete form required to enter the coordination workflow."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1_000)
    description: str = Field(min_length=1, max_length=5_000)
    proposed_date_times: list[AwareDatetime] = Field(min_length=1)
    expected_attendance: int = Field(gt=0)
    venue_requirements: str = Field(min_length=1, max_length=2_000)
    accessibility_needs: str = Field(min_length=1, max_length=2_000)
    equipment_requirements: str = Field(min_length=1, max_length=2_000)
    registration_needs: str = Field(min_length=1, max_length=2_000)


class EventReviewDecision(BaseModel):
    """A coordinator's outcome after reviewing a submitted request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    decision: EventRequestStatus
    reason: str | None = Field(default=None, max_length=2_000)

    @field_validator("decision")
    @classmethod
    def decision_must_close_review(
        cls, value: EventRequestStatus
    ) -> EventRequestStatus:
        allowed = {
            EventRequestStatus.APPROVED,
            EventRequestStatus.CHANGES_REQUESTED,
            EventRequestStatus.REJECTED,
        }
        if value not in allowed:
            raise ValueError("decision must be Approved, Changes Requested, or Rejected")
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def blank_reason_is_missing(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def requires_reason(self) -> bool:
        return self.decision in {
            EventRequestStatus.CHANGES_REQUESTED,
            EventRequestStatus.REJECTED,
        }


class EventClarificationResponse(BaseModel):
    """The organiser's response to the latest clarification request.

    Submitted request fields remain immutable; this response tells the
    coordinator what should be clarified or considered during the next review.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    response: str = Field(min_length=1, max_length=2_000)


class EventChangeRequestStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class EventChangeRequestCreate(BaseModel):
    """The canonical fields an organiser may propose changing after approval."""

    model_config = ConfigDict(str_strip_whitespace=True)

    explanation: str = Field(min_length=1, max_length=2_000)
    proposed_date_times: list[AwareDatetime] | None = Field(default=None, min_length=1)
    expected_attendance: int | None = Field(default=None, gt=0)
    venue_requirements: str | None = Field(default=None, min_length=1, max_length=2_000)
    equipment_requirements: str | None = Field(default=None, min_length=1, max_length=2_000)
    registration_needs: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def proposed_change_is_required(self) -> "EventChangeRequestCreate":
        proposed = self.model_dump(exclude={"explanation"}, exclude_none=True)
        if not proposed:
            raise ValueError("at least one event field must be changed")
        return self

    def proposed_changes(self) -> dict[str, Any]:
        return self.model_dump(
            exclude={"explanation"}, exclude_none=True, mode="json"
        )


class EventChangeBookingPlanItem(BaseModel):
    """Coordinator-chosen actual range for one existing booking, without venue changes."""

    model_config = ConfigDict(extra="forbid")

    booking_id: UUID
    start_date: date
    end_date: date
    start_minute: int = Field(ge=420, le=1425, multiple_of=15)
    end_minute: int = Field(ge=435, le=1440, multiple_of=15)

    @model_validator(mode="after")
    def range_is_valid(self) -> "EventChangeBookingPlanItem":
        if self.end_date < self.start_date or self.end_minute <= self.start_minute:
            raise ValueError("booking end must follow its start within the booking rules")
        return self


class EventChangeBookingConflict(BaseModel):
    """Only authorised, schema-checked conflict facts may cross the API boundary."""

    booking_id: UUID
    # hold_conflict: an active tentative hold (SCRUM-18, 0066) covers the new time.
    refusal_codes: list[Literal[
        "venue_unavailable", "active_block", "setup_outside_window",
        "turnaround_outside_window", "booking_conflict", "hold_conflict",
    ]] = Field(min_length=1)
    conflicting_booking_ids: list[UUID]
    conflicting_block_ids: list[UUID]


class EventChangeDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    decision: EventChangeRequestStatus
    reason: str | None = Field(default=None, max_length=2_000)
    booking_plan: list[EventChangeBookingPlanItem] | None = None

    @field_validator("decision")
    @classmethod
    def decision_must_be_final(
        cls, value: EventChangeRequestStatus
    ) -> EventChangeRequestStatus:
        if value not in {
            EventChangeRequestStatus.APPROVED,
            EventChangeRequestStatus.REJECTED,
        }:
            raise ValueError("decision must be Approved or Rejected")
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def blank_reason_is_missing(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def rejection_requires_reason(self) -> "EventChangeDecision":
        if self.decision == EventChangeRequestStatus.REJECTED and not self.reason:
            raise ValueError("a rejection reason is required")
        if self.booking_plan is not None:
            if self.decision != EventChangeRequestStatus.APPROVED:
                raise ValueError("Booking plan is only supported for date approval")
            ids = [booking.booking_id for booking in self.booking_plan]
            if len(ids) != len(set(ids)):
                raise ValueError("each booking must appear only once in the booking plan")
        return self


class EventFinalEndUpdate(BaseModel):
    """Only the assigned coordinator records the authoritative final end."""

    final_event_end_at: AwareDatetime


class EventRequestResponse(EventRequestFields):
    id: str
    organiser_id: str
    status: EventRequestStatus
    created_at: datetime
    updated_at: datetime
    final_event_end_at: AwareDatetime | None = None


class AttendeeEventResponse(BaseModel):
    id: str
    event_name: str | None
    description: str | None
    status: EventRequestStatus
    proposed_date_times: list[AwareDatetime]


class SafetyTarget(BaseModel):
    """An arrangement the Safety Officer says needs another look (SCRUM-60 AC4)."""

    arrangement: Literal["venue_booking", "equipment_reservation"]
    id: UUID


class SafetyDecision(BaseModel):
    """The Safety Officer's decision on an event in Safety Review (SCRUM-60).

    Reject is parked until the customer defines it, so it is not accepted.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    decision: Literal["approved", "changes_requested", "rejected"]
    reason: str | None = Field(default=None, max_length=2_000)
    targets: list[SafetyTarget] = Field(default_factory=list)

    @model_validator(mode="after")
    def changes_need_a_reason(self) -> "SafetyDecision":
        if self.decision != "approved" and not self.reason:
            raise ValueError("a reason is required unless approving")
        if len({(t.arrangement, t.id) for t in self.targets}) != len(self.targets):
            raise ValueError("each arrangement can be listed only once")
        return self


class SafetyReviewResponse(BaseModel):
    id: str
    event_request_id: str
    decision: Literal["approved", "changes_requested", "rejected"]
    reason: str | None
    targets: list[dict[str, Any]]
    decided_by: str
    decided_at: datetime


class EventReviewDecisionResponse(BaseModel):
    id: int
    event_request_id: str
    coordinator_id: str
    decision_status: EventRequestStatus
    reason: str | None
    decided_at: datetime
    organiser_response: str | None = None
    responded_at: datetime | None = None


class EventChangeRequestResponse(BaseModel):
    id: str
    event_request_id: str
    organiser_id: str
    status: EventChangeRequestStatus
    explanation: str
    proposed_changes: dict[str, Any]
    base_event_updated_at: datetime
    coordinator_id: str | None = None
    decision_reason: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    applied_booking_plan: list[EventChangeBookingPlanItem] | None = None


class EventChangeDatePlanBooking(BaseModel):
    """Advisory date candidates; existing booking identity and minutes stay fixed."""

    booking_id: str
    venue_id: str
    status: Literal["pending", "approved"]
    current_start_date: date
    current_end_date: date
    proposed_start_date: date
    proposed_end_date: date
    start_minute: int
    end_minute: int


class EventChangeDatePlanResponse(BaseModel):
    """A read snapshot, never an availability verdict or permission to approve."""

    event_request_id: str
    change_request_id: str
    advisory: Literal[True] = True
    bookings: list[EventChangeDatePlanBooking]


class EventChangeBookingContextItem(EventChangeBookingPlanItem):
    """Current booking identity/range only; no editable venue or admin metadata."""

    venue_id: UUID
    status: Literal["pending", "approved"]


class EventChangeBookingContext(BaseModel):
    event_request_id: str
    change_request_id: str
    event_updated_at: AwareDatetime
    bookings: list[EventChangeBookingContextItem]
    automatic_plan: list[EventChangeBookingPlanItem] | None = None
    automatic_plan_error: Literal["unsupported_date_mapping", "no_op_date_mapping"] | None = None


class HealthResponse(BaseModel):
    service: str
    status: str


class EventStatusHistoryResponse(BaseModel):
    """Read-only status evidence; baseline rows explicitly identify legacy events."""

    id: int
    event_request_id: str
    previous_status: EventRequestStatus | None
    new_status: EventRequestStatus
    actor_id: str | None
    actor_role: str
    source: str
    entry_kind: Literal["created", "transition", "baseline"]
    occurred_at: AwareDatetime
