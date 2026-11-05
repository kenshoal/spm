"""Venue block schemas; persistence and booking impact are separate concerns.

Dates are inclusive. The start and end time are blocked on every date in the
range, in minutes after midnight in 15-minute steps within 07:00-24:00
(SCRUM-65; a full day is 420-1440).
"""

from datetime import UTC, date, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Slot
from app.slots import check_time_range, slots_to_range, touched_slots


class BlockReason(str, Enum):
    MAINTENANCE = "maintenance"
    RENOVATION = "renovation"
    SAFETY = "safety"
    INTERNAL_USE = "internal_use"
    EQUIPMENT_FAILURE = "equipment_failure"
    OTHER = "other"


class BlockStatus(str, Enum):
    """Lifted means explicitly withdrawn, not merely a period in the past."""

    ACTIVE = "active"
    LIFTED = "lifted"


class VenueBlockCreate(BaseModel):
    """Staff input only; venue and creator identity are supplied by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start_date: date
    end_date: date
    start_minute: int
    end_minute: int
    reason_category: BlockReason
    # Team-proposed input limit, not a customer-mandated business rule.
    reason_detail: str | None = Field(default=None, max_length=1000)

    @field_validator("reason_detail")
    @classmethod
    def normalize_detail(cls, detail: str | None) -> str | None:
        return detail or None

    @model_validator(mode="after")
    def validate_dates_and_times(self) -> "VenueBlockCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        check_time_range(self.start_minute, self.end_minute)
        return self


class VenueBlock(BaseModel):
    """Stored/read shape. Routes accept VenueBlockCreate as input.

    An active record only restricts its dates and times. ``slots`` are the slots
    the time touches, kept for slot-based readers (SCRUM-31's calendar); given
    alone (rows before 0051), they convert to their time range.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    venue_id: str = Field(min_length=1)
    start_date: date
    end_date: date
    start_minute: int | None = None
    end_minute: int | None = None
    slots: list[Slot] = Field(default_factory=list)
    reason_category: BlockReason
    reason_detail: str | None = None
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: BlockStatus = BlockStatus.ACTIVE

    @model_validator(mode="after")
    def _times_and_slots(self) -> "VenueBlock":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.start_minute is None or self.end_minute is None:
            self.start_minute, self.end_minute = slots_to_range(self.slots)
        self.slots = touched_slots(self.start_minute, self.end_minute)
        return self
