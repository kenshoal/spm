"""Venue block schemas; persistence and booking impact are separate concerns.

Dates are inclusive. The selected slots are blocked on every date in the range.
A full-day block selects AM, PM and NIGHT; NIGHT belongs to its starting date.
"""

from datetime import UTC, date, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Slot


class BlockReason(str, Enum):
    MAINTENANCE = "maintenance"
    RENOVATION = "renovation"
    SAFETY = "safety"
    INTERNAL_USE = "internal_use"


class BlockStatus(str, Enum):
    """Lifted means explicitly withdrawn, not merely a period in the past."""

    ACTIVE = "active"
    LIFTED = "lifted"


class VenueBlockCreate(BaseModel):
    """Staff input only; venue and creator identity are supplied by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start_date: date
    end_date: date
    slots: list[Slot] = Field(min_length=1)
    reason_category: BlockReason
    # Team-proposed input limit, not a customer-mandated business rule.
    reason_detail: str | None = Field(default=None, max_length=1000)

    @field_validator("slots")
    @classmethod
    def validate_slots(cls, slots: list[Slot]) -> list[Slot]:
        if len(slots) != len(set(slots)):
            raise ValueError("slots must not contain duplicates")
        return [slot for slot in (Slot.AM, Slot.PM, Slot.NIGHT) if slot in slots]

    @field_validator("reason_detail")
    @classmethod
    def normalize_detail(cls, detail: str | None) -> str | None:
        return detail or None

    @model_validator(mode="after")
    def validate_dates(self) -> "VenueBlockCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class VenueBlock(VenueBlockCreate):
    """Stored/read shape. Future routes must accept VenueBlockCreate as input.

    An active record only restricts its specified dates and slots. These fields do
    not implement storage, authorization, overlap checks or notification delivery.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    venue_id: str = Field(min_length=1)
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: BlockStatus = BlockStatus.ACTIVE
