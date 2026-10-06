"""Requests and results for venue-block checks, not booking creation."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Slot


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    slots: list[Slot] = Field(min_length=1)

    @field_validator("slots")
    @classmethod
    def validate_slots(cls, slots: list[Slot]) -> list[Slot]:
        if len(set(slots)) != len(slots):
            raise ValueError("slots must not contain duplicates")
        return [slot for slot in Slot if slot in slots]

    @model_validator(mode="after")
    def validate_dates(self) -> "Period":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class BlockConflict(Period):
    block_id: str


class AvailabilityResult(BaseModel):
    venue_id: str
    available: bool
    reasons: list[
        Literal["venue_unavailable", "outside_operating_slots", "active_block"]
    ]
    unsupported_slots: list[Slot]
    conflicts: list[BlockConflict]
