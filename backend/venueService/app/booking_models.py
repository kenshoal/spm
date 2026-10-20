"""Models for venue booking requests (SCRUM-32).

A request is an Event Coordinator's ask for a venue, a date range and a start
and end time that apply on each date (SCRUM-65). Times are minutes after
midnight in 15-minute steps within 07:00-24:00 (420-1440). Submitting creates a
pending request and reserves nothing. Tables:
``database/migrations/0018_venue_booking_requests.sql`` and
``0050_venue_booking_times.sql``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models import Slot, _now
from app.slots import slots_to_range, touched_slots

OPEN_MINUTE, CLOSE_MINUTE, STEP_MINUTES = 420, 1440, 15


class BookingRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class BookingRequestCreate(BaseModel):
    """What a Coordinator may send. Everything else is set by the service."""

    model_config = ConfigDict(extra="forbid")

    venue_id: str = Field(min_length=1)
    event_request_id: UUID
    start_date: date
    end_date: date
    start_minute: int
    end_minute: int

    @field_validator("end_date")
    @classmethod
    def _end_not_before_start(cls, value: date, info: ValidationInfo) -> date:
        start = info.data.get("start_date")
        if start is not None and value < start:
            raise ValueError("end_date must not be before start_date")
        return value

    @model_validator(mode="after")
    def _valid_times(self) -> BookingRequestCreate:
        # The codes match SCRUM-20's check_booking_time; the database checks
        # the same rules (0050).
        start, end = self.start_minute, self.end_minute
        if start % STEP_MINUTES or end % STEP_MINUTES:
            raise PydanticCustomError("off_step", "Times must be on a 15-minute step.")
        if start < OPEN_MINUTE or end > CLOSE_MINUTE:
            raise PydanticCustomError(
                "outside_operating_window", "Bookings must fall between 07:00 and 24:00."
            )
        if end <= start:
            raise PydanticCustomError(
                "end_not_after_start", "The end must be after the start."
            )
        return self


class BookingRequest(BaseModel):
    """A stored booking request."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    venue_id: str
    requested_by: str
    event_request_id: str
    event_name: str | None = None
    expected_attendance: int | None = None
    requirements_note: str | None = None
    start_date: date
    end_date: date
    start_minute: int | None = None
    end_minute: int | None = None
    # Until Sprint 4 the slots a booking's time touches, for slot-based readers.
    # Given alone (stored rows before 0050), they convert to the time range.
    slots: list[Slot] = Field(default_factory=list)
    status: BookingRequestStatus = BookingRequestStatus.PENDING
    decision_reason: str | None = None
    suggested_alternative: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    cancelled_by: str | None = None
    cancelled_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def _times_and_slots(self) -> BookingRequest:
        if self.start_minute is None or self.end_minute is None:
            self.start_minute, self.end_minute = slots_to_range(self.slots)
        self.slots = touched_slots(self.start_minute, self.end_minute)
        return self
