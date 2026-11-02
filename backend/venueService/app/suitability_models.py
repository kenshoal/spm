"""Requests and results for the venue suitability check.

Advisory only: comparing an event's requirements against a venue's recorded
attributes never books, holds, or otherwise changes the venue.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.models import RoomLayout
from app.slots import check_time_range

SuitabilityAttribute = Literal[
    "capacity", "layout", "facilities", "accessibility", "operating_hours"
]


class SuitabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_attendance: int = Field(gt=0)
    required_layout: RoomLayout | None = None
    # An optional time on 15-minute steps within the fixed 07:00-24:00 window
    # every venue operates (SCRUM-65); an invalid time is refused with 422.
    required_start_minute: int | None = None
    required_end_minute: int | None = None
    required_facilities: list[str] = Field(default_factory=list)
    required_accessibility: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid_time(self) -> SuitabilityRequest:
        start, end = self.required_start_minute, self.required_end_minute
        if start is None and end is None:
            return self
        if start is None or end is None:
            raise PydanticCustomError(
                "times_incomplete", "Give both a start and an end time."
            )
        check_time_range(start, end)
        return self


class SuitabilityMismatch(BaseModel):
    attribute: SuitabilityAttribute
    reason: str


class SuitabilityResult(BaseModel):
    venue_id: str
    suitable: bool
    mismatches: list[SuitabilityMismatch]
