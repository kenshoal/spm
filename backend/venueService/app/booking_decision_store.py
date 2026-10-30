"""Decisions on venue booking requests (SCRUM-15) and the refusal log.

``VENUE_STORAGE_BACKEND`` selects the store, as for venues and bookings:

* ``memory``: applies ``assess_booking_decision`` under the process-wide venue
  lock and keeps refusals in process memory. Used by the unit tests.
* ``supabase``: calls ``decide_venue_booking_request``
  (``database/migrations/0024_venue_booking_decisions.sql``), which locks the
  venue and request rows and re-checks the same rules in one transaction.

An approved request is the confirmed booking (0018). A refused approval leaves
the request pending and records one refusal with the reasons (AC5).
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any, Literal, Protocol
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from app.block_repository import block_repository
from app.booking_decisions import (
    BookingDecisionSubject,
    ConfirmedVenueBooking,
    DecisionDetails,
    assess_booking_decision,
)
from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import booking_repository
from app.config import get_settings
from app.hold_store import memory_hold_store
from app.models import _now
from app.repository import repository
from app.supabase_repository import SupabaseRepositoryError, _is_uuid
from app.venue_locks import venue_write_lock

RefusalCode = Literal[
    "venue_unavailable",
    "outside_operating_slots",
    "active_block",
    "setup_outside_window",
    "turnaround_outside_window",
    "booking_conflict",
    "hold_conflict",
]


class BookingRefusal(BaseModel):
    """One refused approval: who tried, when, and why."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    booking_request_id: str
    refused_by: str
    refusal_codes: list[RefusalCode]
    conflicting_block_ids: list[str] = Field(default_factory=list)
    conflicting_booking_ids: list[str] = Field(default_factory=list)
    conflicting_hold_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class DecisionOutcome(BaseModel):
    """The request after the attempt; refusal details when approval was refused."""

    booking: BookingRequest
    refused: bool = False
    refusal_codes: list[RefusalCode] = Field(default_factory=list)
    conflicting_block_ids: list[str] = Field(default_factory=list)
    conflicting_booking_ids: list[str] = Field(default_factory=list)
    conflicting_hold_ids: list[str] = Field(default_factory=list)


class BookingNotFoundError(Exception):
    """The booking request does not exist."""


class BookingAlreadyDecidedError(Exception):
    """The booking request is no longer pending."""


class BookingDecisionStore(Protocol):
    def decide(
        self, booking_id: str, details: DecisionDetails, decided_by: str
    ) -> DecisionOutcome: ...
    def list_refusals(self, booking_id: str) -> list[BookingRefusal]: ...


class MemoryBookingDecisionStore:
    """Decides requests held in the in-memory booking store."""

    def __init__(self) -> None:
        self._refusals: list[BookingRefusal] = []

    def decide(
        self, booking_id: str, details: DecisionDetails, decided_by: str
    ) -> DecisionOutcome:
        booking = booking_repository.get(booking_id)
        if booking is None:
            raise BookingNotFoundError
        with venue_write_lock:
            if booking.status is not BookingRequestStatus.PENDING:
                raise BookingAlreadyDecidedError
            venue = repository.get(booking.venue_id)
            if venue is None:
                raise BookingNotFoundError
            approved = booking_repository.list_by_status(BookingRequestStatus.APPROVED)
            assessment = assess_booking_decision(
                booking=BookingDecisionSubject(
                    venue_id=booking.venue_id,
                    current_status=booking.status.value,
                    start_date=booking.start_date,
                    end_date=booking.end_date,
                    slots=booking.slots,
                    start_minute=booking.start_minute,
                    end_minute=booking.end_minute,
                ),
                decision=details,
                venue=venue,
                blocks=block_repository.list_for_venue(booking.venue_id),
                confirmed_bookings=[
                    ConfirmedVenueBooking(
                        booking_id=other.id,
                        venue_id=other.venue_id,
                        start_date=other.start_date,
                        end_date=other.end_date,
                        slots=other.slots,
                        start_minute=other.start_minute,
                        end_minute=other.end_minute,
                    )
                    for other in approved
                    if other.id != booking.id
                ],
                holds=memory_hold_store.protecting(booking.venue_id, booking.event_request_id),
            )
            if not assessment.allowed:
                refusal = BookingRefusal(
                    booking_request_id=booking.id,
                    refused_by=decided_by,
                    refusal_codes=assessment.refusal_codes,
                    conflicting_block_ids=sorted(
                        {c.block_id for c in assessment.availability.conflicts}
                        if assessment.availability
                        else set()
                    ),
                    conflicting_booking_ids=assessment.conflicting_booking_ids,
                    conflicting_hold_ids=assessment.conflicting_hold_ids,
                )
                self._refusals.append(refusal)
                return DecisionOutcome(
                    booking=booking.model_copy(),
                    refused=True,
                    refusal_codes=refusal.refusal_codes,
                    conflicting_block_ids=refusal.conflicting_block_ids,
                    conflicting_booking_ids=refusal.conflicting_booking_ids,
                    conflicting_hold_ids=refusal.conflicting_hold_ids,
                )
            booking.status = BookingRequestStatus(assessment.target_status)
            booking.decision_reason = assessment.reason
            booking.suggested_alternative = assessment.suggested_alternative
            booking.decided_by = decided_by
            booking.decided_at = _now()
            memory_hold_store.close_for_decision(booking, decided_by)
            return DecisionOutcome(booking=booking.model_copy())

    def list_refusals(self, booking_id: str) -> list[BookingRefusal]:
        return [r for r in self._refusals if r.booking_request_id == booking_id]

    def clear(self) -> None:
        self._refusals.clear()


class SupabaseBookingDecisionStore:
    """Calls the 0024 database function through Supabase's Data API."""

    def __init__(
        self,
        url: str,
        secret_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            timeout=10,
            transport=transport,
        )

    def _send(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError("Venue store unavailable") from error
        if response.is_success:
            return response.json() if response.content else None
        try:
            code = response.json().get("code")
        except (ValueError, AttributeError):
            code = None
        if code == "P0002":
            raise BookingNotFoundError
        if code == "55000":
            raise BookingAlreadyDecidedError
        raise SupabaseRepositoryError(
            f"Venue store request failed ({response.status_code})"
        )

    def decide(
        self, booking_id: str, details: DecisionDetails, decided_by: str
    ) -> DecisionOutcome:
        # Postgres rejects a malformed uuid literal; an unknown id is simply absent.
        if not _is_uuid(booking_id):
            raise BookingNotFoundError
        body = self._send(
            "POST",
            "/rpc/decide_venue_booking_request",
            json={
                "p_booking_request_id": booking_id,
                "p_decision": details.decision,
                "p_decided_by": decided_by,
                "p_decision_reason": details.reason,
                "p_suggested_alternative": details.suggested_alternative,
            },
        )
        if not isinstance(body, dict) or "booking" not in body:
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        booking = BookingRequest.model_validate(body["booking"])
        if body.get("outcome") == "refused":
            return DecisionOutcome(
                booking=booking,
                refused=True,
                refusal_codes=body.get("refusal_codes", []),
                conflicting_block_ids=body.get("conflicting_block_ids", []),
                conflicting_booking_ids=body.get("conflicting_booking_ids", []),
                conflicting_hold_ids=body.get("conflicting_hold_ids", []),
            )
        return DecisionOutcome(booking=booking)

    def list_refusals(self, booking_id: str) -> list[BookingRefusal]:
        if not _is_uuid(booking_id):
            return []
        rows = self._send(
            "GET",
            "/venue_booking_refusals",
            params={
                "booking_request_id": f"eq.{booking_id}",
                "select": "*",
                "order": "created_at.asc,id.asc",
            },
        )
        if not isinstance(rows, list):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return [BookingRefusal.model_validate(row) for row in rows]


# Module-level singleton used when VENUE_STORAGE_BACKEND=memory.
memory_decision_store = MemoryBookingDecisionStore()


@lru_cache
def _supabase_decision_store() -> BookingDecisionStore:
    settings = get_settings()
    return SupabaseBookingDecisionStore(
        str(settings.supabase_url),
        settings.supabase_secret_key.get_secret_value(),
    )


def get_booking_decision_store() -> BookingDecisionStore:
    """FastAPI dependency returning the configured decision store."""

    if get_settings().venue_storage_backend == "supabase":
        return _supabase_decision_store()
    return memory_decision_store
