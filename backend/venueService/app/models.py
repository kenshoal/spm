"""Pydantic models for the venue catalogue.

Grounded in the customer briefing (section 4, "Venue Catalogue" and "Room Layout
Management") and the accepted clarification that venues are booked in AM / PM /
Night slots (GitHub discussion #50). Setup and turnaround times are minutes in
15-minute increments (Week 7 Change #1; discussion #131).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def _now() -> datetime:
    return datetime.now(UTC)


# The 07:00-24:00 operating window (discussion #131) is 1020 minutes.
MAX_PREP_MINUTES = 1020

PrepMinutes = Annotated[int, Field(ge=0, le=MAX_PREP_MINUTES, multiple_of=15)]
"""Setup or turnaround time in minutes: a multiple of 15 from 0 to 1020."""

# A venue's daily operating start and end sit on 15-minute steps inside 07:00-24:00
# (SCRUM-30 AC1, Q&A #46 and #131: 07:00 to 24:00 stays the outer bound).
DAY_OPEN_MINUTE = 7 * 60
DAY_CLOSE_MINUTE = 24 * 60
OperatingMinute = Annotated[
    int, Field(ge=DAY_OPEN_MINUTE, le=DAY_CLOSE_MINUTE, multiple_of=15)
]
"""A minute after midnight on a 15-minute step from 07:00 to 24:00."""


def _hours_are_ordered(start: int, end: int) -> None:
    if start >= end:
        raise ValueError("operating_start_minute must be before operating_end_minute")


class RoomLayout(str, Enum):
    """Layouts a venue may support (briefing section 4, Room Layout Management)."""

    CLASSROOM = "classroom"
    THEATRE = "theatre"
    BOARDROOM = "boardroom"
    BANQUET = "banquet"
    EXHIBITION = "exhibition"


class Slot(str, Enum):
    """Booking slots. A full-day booking occupies all three (discussion #50)."""

    AM = "AM"
    PM = "PM"
    NIGHT = "NIGHT"


class VenueStatus(str, Enum):
    """Whole-venue operational status.

    Per-date-slot blocking (the availability calendar) is a separate concern
    owned by other stories; this flag is the minimum needed for search to
    exclude an unavailable venue.
    """

    AVAILABLE = "available"
    BLOCKED = "blocked"


def _positive_layout_capacities(
    value: dict[RoomLayout, int],
) -> dict[RoomLayout, int]:
    if any(capacity <= 0 for capacity in value.values()):
        raise ValueError("Each layout's capacity must be a positive whole number")
    return value


class VenueBase(BaseModel):
    name: str = Field(min_length=1)
    location: str = Field(min_length=1)
    max_capacity: int = Field(gt=0)
    facilities: list[str] = Field(default_factory=list)
    accessibility_features: list[str] = Field(default_factory=list)
    supported_layouts: list[RoomLayout] = Field(default_factory=list)
    # Hotfix 12 (Q&A #112): capacity per layout. A layout with no entry uses max_capacity.
    layout_capacities: dict[RoomLayout, int] = Field(default_factory=dict)
    operating_slots: list[Slot] = Field(
        default_factory=lambda: [Slot.AM, Slot.PM, Slot.NIGHT]
    )
    # 0 means none; venues start with none until Venue Staff set one (SCRUM-59).
    setup_minutes: PrepMinutes = 0
    turnaround_minutes: PrepMinutes = 0
    # SCRUM-30 AC1: one daily operating start and end. A venue created without them
    # operates the whole 07:00-24:00 day. Time outside them is never free.
    operating_start_minute: OperatingMinute = DAY_OPEN_MINUTE
    operating_end_minute: OperatingMinute = DAY_CLOSE_MINUTE

    @model_validator(mode="after")
    def _operating_hours_are_ordered(self) -> VenueBase:
        _hours_are_ordered(self.operating_start_minute, self.operating_end_minute)
        return self

    def is_open_for(self, start_minute: int, end_minute: int) -> bool:
        """Whether a time range lies wholly inside the venue's operating hours."""
        return (
            self.operating_start_minute <= start_minute
            and end_minute <= self.operating_end_minute
        )

    @field_validator("layout_capacities")
    @classmethod
    def _layout_capacities_are_positive(
        cls, value: dict[RoomLayout, int]
    ) -> dict[RoomLayout, int]:
        return _positive_layout_capacities(value)

    def capacity_for(self, layout: RoomLayout | None) -> int:
        """The capacity to judge an event by: the layout's own when it has one."""
        if layout is None:
            return self.max_capacity
        return self.layout_capacities.get(layout, self.max_capacity)


class VenueCreate(VenueBase):
    """Payload for creating a venue record."""


class VenueUpdate(BaseModel):
    """Partial update payload; unset fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1)
    location: str | None = Field(default=None, min_length=1)
    max_capacity: int | None = Field(default=None, gt=0)
    facilities: list[str] | None = None
    accessibility_features: list[str] | None = None
    supported_layouts: list[RoomLayout] | None = None
    layout_capacities: dict[RoomLayout, int] | None = None
    operating_slots: list[Slot] | None = None
    status: VenueStatus | None = None
    setup_minutes: PrepMinutes | None = None
    turnaround_minutes: PrepMinutes | None = None
    operating_start_minute: OperatingMinute | None = None
    operating_end_minute: OperatingMinute | None = None

    @field_validator("layout_capacities")
    @classmethod
    def _update_layout_capacities_are_positive(
        cls, value: dict[RoomLayout, int] | None
    ) -> dict[RoomLayout, int] | None:
        return None if value is None else _positive_layout_capacities(value)

    @field_validator(
        "setup_minutes", "turnaround_minutes", "operating_start_minute", "operating_end_minute"
    )
    @classmethod
    def _times_are_not_null(cls, value: int | None) -> int:
        # Omitting a time leaves it unchanged; sending null is refused.
        if value is None:
            raise ValueError("must be a number of minutes, not null")
        return value

    @model_validator(mode="after")
    def _named_hours_are_ordered(self) -> VenueUpdate:
        start, end = self.operating_start_minute, self.operating_end_minute
        if start is not None and end is not None:
            _hours_are_ordered(start, end)
        return self


class Venue(VenueBase):
    """A stored venue record."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    status: VenueStatus = VenueStatus.AVAILABLE
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class VenueSearchResult(Venue):
    """A venue search match. ``tentatively_held`` marks a venue that is free at
    the searched time except for active tentative holds (SCRUM-18 AC6)."""

    tentatively_held: bool = False


class VenueLocation(BaseModel):
    """The minimum venue facts other services need to place equipment (SCRUM-13 D11)."""

    id: str
    name: str
    location: str
