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

from pydantic import BaseModel, Field, field_validator


def _now() -> datetime:
    return datetime.now(UTC)


# The 07:00-24:00 operating window (discussion #131) is 1020 minutes.
MAX_PREP_MINUTES = 1020

PrepMinutes = Annotated[int, Field(ge=0, le=MAX_PREP_MINUTES, multiple_of=15)]
"""Setup or turnaround time in minutes: a multiple of 15 from 0 to 1020."""


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


class VenueBase(BaseModel):
    name: str = Field(min_length=1)
    location: str = Field(min_length=1)
    max_capacity: int = Field(gt=0)
    facilities: list[str] = Field(default_factory=list)
    accessibility_features: list[str] = Field(default_factory=list)
    supported_layouts: list[RoomLayout] = Field(default_factory=list)
    operating_slots: list[Slot] = Field(
        default_factory=lambda: [Slot.AM, Slot.PM, Slot.NIGHT]
    )
    # 0 means none; venues start with none until Venue Staff set one (SCRUM-59).
    setup_minutes: PrepMinutes = 0
    turnaround_minutes: PrepMinutes = 0


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
    operating_slots: list[Slot] | None = None
    status: VenueStatus | None = None
    setup_minutes: PrepMinutes | None = None
    turnaround_minutes: PrepMinutes | None = None

    @field_validator("setup_minutes", "turnaround_minutes")
    @classmethod
    def _times_are_not_null(cls, value: int | None) -> int:
        # Omitting a time leaves it unchanged; sending null is refused.
        if value is None:
            raise ValueError("must be a number of minutes, not null")
        return value


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
