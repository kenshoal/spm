"""Tentative venue holds (SCRUM-18; Week 7 Customer Change #4).

A hold uses the booking time rules (SCRUM-65) and expires at most 7 days ahead.
It protects its time only while active and unexpired, the same rule as the
database (0066): ``status == "active" and expires_at > now``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.slots import check_time_range

MAX_HOLD = timedelta(days=7)
# Event statuses in which a hold may be placed: approved, not yet confirmed.
HOLDABLE_EVENT_STATUSES = frozenset({"Approved", "Planning", "Safety Review"})


class HoldStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    CONVERTED = "converted"
    EXPIRED = "expired"


class VenueHoldCreate(BaseModel):
    """What a Coordinator sends to hold a venue for their event."""

    model_config = ConfigDict(extra="forbid")

    event_request_id: UUID
    start_date: date
    end_date: date
    start_minute: int
    end_minute: int
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def _valid_times(self) -> VenueHoldCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        check_time_range(self.start_minute, self.end_minute)
        return self


class VenueHold(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    venue_id: str
    event_request_id: str
    start_date: date
    end_date: date
    start_minute: int
    end_minute: int
    expires_at: AwareDatetime
    status: HoldStatus = HoldStatus.ACTIVE
    booking_request_id: str | None = None
    placed_by: str
    placed_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: AwareDatetime | None = None
    closed_by: str | None = None

    def protects(self, now: datetime) -> bool:
        """Whether the hold still keeps its time from other holds and bookings."""
        return self.status is HoldStatus.ACTIVE and self.expires_at > now


HoldRefusalCode = Literal[
    "venue_unavailable",
    "active_block",
    "setup_outside_window",
    "turnaround_outside_window",
    "outside_operating_hours",
    "booking_conflict",
    "hold_conflict",
]


class HoldPlacement(BaseModel):
    """A placed hold, or the reasons it was refused."""

    hold: VenueHold | None = None
    refusal_codes: list[HoldRefusalCode] = []
    conflicting_block_ids: list[str] = []
    conflicting_booking_ids: list[str] = []
    conflicting_hold_ids: list[str] = []


class HoldNotice(BaseModel):
    """A due "expiring" or "expired" notice for the event's coordinator."""

    hold_id: str
    kind: Literal["expiring", "expired"]
    recipient_id: str
    venue_id: str
    venue_name: str | None = None
    event_request_id: str
    event_name: str | None = None
    start_date: date
    end_date: date
    start_minute: int
    end_minute: int
    expires_at: AwareDatetime


def expiry_error(expires_at: datetime, now: datetime) -> str | None:
    """Why an expiry is not allowed, or None: it must be within the next 7 days."""
    if expires_at <= now:
        return "The hold must expire in the future."
    if expires_at > now + MAX_HOLD:
        return "A hold can last at most 7 days."
    return None
