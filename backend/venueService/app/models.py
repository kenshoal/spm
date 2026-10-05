"""Pydantic models for the venue catalogue.

Grounded in the customer briefing (section 4, "Venue Catalogue" and "Room Layout
Management") and the accepted clarification that venues are booked in AM / PM /
Night slots (GitHub discussion #50).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


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


class Venue(VenueBase):
    """A stored venue record."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    status: VenueStatus = VenueStatus.AVAILABLE
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class VenueBookingRequest(BaseModel):
    """Read projection of a SCRUM-32 venue_booking_requests row for Venue Staff.

    event_name, expected_attendance and requirements_note are the snapshot
    SCRUM-32 takes at submission, so Venue Staff never read the event request.
    """

    id: str
    venue_id: str
    event_request_id: str
    event_name: str | None
    expected_attendance: int | None
    requirements_note: str | None
    start_date: date
    end_date: date
    slots: list[Slot]
    status: Literal["pending", "approved", "rejected"]
    decision_reason: str | None
    suggested_alternative: str | None
    requested_by: str
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime