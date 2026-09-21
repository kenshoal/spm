from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class EventRequestStatus(str, Enum):
    """The full status set is the team's agreed design (backlog C-2, not yet
    built here) — see spm-brain/backlog/user-stories.md. Only Draft and
    Submitted have real transitions implemented so far; the rest are added
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


class EventRequestResponse(EventRequestFields):
    id: str
    organiser_id: str
    status: EventRequestStatus
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    service: str
    status: str
