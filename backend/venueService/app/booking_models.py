"""Models for venue booking requests (SCRUM-32).

A request is an Event Coordinator's ask for a venue, a date range and slots.
Submitting creates a pending request and reserves nothing. Table:
``database/migrations/0018_venue_booking_requests.sql``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models import Slot, _now


class BookingRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class BookingRequestCreate(BaseModel):
    """What a Coordinator may send. Everything else is set by the service."""

    model_config = ConfigDict(extra="forbid")

    venue_id: str = Field(min_length=1)
    event_request_id: UUID
    start_date: date
    end_date: date
    slots: list[Slot] = Field(min_length=1)

    @field_validator("end_date")
    @classmethod
    def _end_not_before_start(cls, value: date, info: ValidationInfo) -> date:
        start = info.data.get("start_date")
        if start is not None and value < start:
            raise ValueError("end_date must not be before start_date")
        return value

    @field_validator("slots")
    @classmethod
    def _no_duplicate_slots(cls, value: list[Slot]) -> list[Slot]:
        if len(set(value)) != len(value):
            raise ValueError("slots must not contain duplicates")
        return value


class BookingRequest(BaseModel):
    """A stored booking request."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    venue_id: str
    requested_by: str
    event_request_id: str
    event_name: str | None = None
    expected_attendance: int | None = None
    requirements_note: str | None = None
    start_date: date
    end_date: date
    slots: list[Slot]
    status: BookingRequestStatus = BookingRequestStatus.PENDING
    decision_reason: str | None = None
    suggested_alternative: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    cancelled_by: str | None = None
    cancelled_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
