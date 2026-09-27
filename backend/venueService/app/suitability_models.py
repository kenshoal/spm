"""Requests and results for the venue suitability check.

Advisory only: comparing an event's requirements against a venue's recorded
attributes never books, holds, or otherwise changes the venue.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import RoomLayout, Slot

SuitabilityAttribute = Literal[
    "capacity", "layout", "operating_slot", "facilities", "accessibility"
]


class SuitabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_attendance: int = Field(gt=0)
    required_layout: RoomLayout | None = None
    required_slot: Slot | None = None
    required_facilities: list[str] = Field(default_factory=list)
    required_accessibility: list[str] = Field(default_factory=list)


class SuitabilityMismatch(BaseModel):
    attribute: SuitabilityAttribute
    reason: str


class SuitabilityResult(BaseModel):
    venue_id: str
    suitable: bool
    mismatches: list[SuitabilityMismatch]
