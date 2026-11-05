"""Requests and results for venue availability checks, not booking creation.

A period is an inclusive date range with one start and end time on each date,
in minutes after midnight (SCRUM-65).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.slots import check_time_range


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    start_minute: int
    end_minute: int

    @model_validator(mode="after")
    def validate_dates_and_times(self) -> "Period":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        check_time_range(self.start_minute, self.end_minute)
        return self


class BlockConflict(Period):
    """The part of an active block that a requested period shares."""

    block_id: str


class BookingOverlap(Period):
    """The part of an approved booking (SCRUM-15) that a requested period shares,
    setup and turnaround included (SCRUM-66)."""

    booking_id: str


class HoldOverlap(Period):
    """The part of an active tentative hold (SCRUM-18) that a requested period
    shares, setup and turnaround included."""

    hold_id: str


class AvailabilityResult(BaseModel):
    venue_id: str
    available: bool
    reasons: list[
        Literal[
            "venue_unavailable",
            "active_block",
            "setup_outside_window",
            "turnaround_outside_window",
            "outside_operating_hours",
            "booking_conflict",
            "hold_conflict",
        ]
    ]
    conflicts: list[BlockConflict]
    booking_conflicts: list[BookingOverlap] = []
    hold_conflicts: list[HoldOverlap] = []
