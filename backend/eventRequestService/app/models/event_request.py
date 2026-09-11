from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventRequestStatus(str, Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"


class EventRequestFields(BaseModel):
    """Fields that may be recorded while an event request is a draft."""

    model_config = ConfigDict(str_strip_whitespace=True)

    event_name: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=1_000)
    description: str | None = Field(default=None, max_length=5_000)
    proposed_date_times: list[datetime] = Field(default_factory=list)
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
    proposed_date_times: list[datetime] | None = None
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


class EventRequestResponse(EventRequestFields):
    id: str
    organiser_id: str
    status: EventRequestStatus
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    service: str
    status: str

