"""Booking-request stores and storage selection.

Same shape as ``app.repository``: the routers depend on ``BookingRequestStore``
and ``VENUE_STORAGE_BACKEND`` selects the in-memory store (default, tests) or
the Supabase store.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Protocol

from app.booking_models import BookingRequest, BookingRequestStatus
from app.config import get_settings
from app.models import _now
from app.venue_locks import venue_write_lock


class BookingRequestNotFoundError(Exception):
    """The booking request does not exist."""


class BookingNotCancellableError(Exception):
    """Only a pending or approved booking request can be cancelled."""


class BookingRequestStore(Protocol):
    def create(self, booking: BookingRequest) -> BookingRequest: ...
    def get(self, booking_id: str) -> BookingRequest | None: ...
    def list_by_status(
        self, status: BookingRequestStatus | str
    ) -> list[BookingRequest]: ...
    def list_for_requester(self, user_id: str) -> list[BookingRequest]: ...
    def list_for_event(self, event_request_id: str) -> list[BookingRequest]: ...
    def cancel(self, booking_id: str, cancelled_by: str) -> BookingRequest: ...
    def list_approved_for_venue(
        self, venue_id: str, start_date: date, end_date: date
    ) -> list[BookingRequest]: ...


class BookingRequestRepository:
    """In-memory booking-request store."""

    def __init__(self) -> None:
        self._items: list[BookingRequest] = []

    def create(self, booking: BookingRequest) -> BookingRequest:
        self._items.append(booking)
        return booking

    def get(self, booking_id: str) -> BookingRequest | None:
        return next((item for item in self._items if item.id == booking_id), None)

    def list_by_status(
        self, status: BookingRequestStatus | str
    ) -> list[BookingRequest]:
        wanted = BookingRequestStatus(status)
        matching = [item for item in self._items if item.status == wanted]
        # sorted() is stable, so equal timestamps keep submission order.
        return sorted(matching, key=lambda item: item.created_at)

    def list_for_requester(self, user_id: str) -> list[BookingRequest]:
        # The submission position breaks ties, so equal timestamps list the
        # later submission first.
        own = [
            (item.created_at, position, item)
            for position, item in enumerate(self._items)
            if item.requested_by == user_id
        ]
        ordered = sorted(own, key=lambda row: row[:2], reverse=True)
        return [item for _, _, item in ordered]

    def list_for_event(self, event_request_id: str) -> list[BookingRequest]:
        matching = [
            item for item in self._items if item.event_request_id == event_request_id
        ]
        # sorted() is stable, so equal timestamps keep submission order.
        return sorted(matching, key=lambda item: item.created_at)

    def cancel(self, booking_id: str, cancelled_by: str) -> BookingRequest:
        # The venue lock keeps a cancel and an approval from interleaving, as
        # the database function does by locking the request row.
        with venue_write_lock:
            booking = self.get(booking_id)
            if booking is None:
                raise BookingRequestNotFoundError
            if booking.status not in (
                BookingRequestStatus.PENDING,
                BookingRequestStatus.APPROVED,
            ):
                raise BookingNotCancellableError
            booking.status = BookingRequestStatus.CANCELLED
            booking.cancelled_by = cancelled_by
            booking.cancelled_at = _now()
            return booking.model_copy()

    def list_approved_for_venue(
        self, venue_id: str, start_date: date, end_date: date
    ) -> list[BookingRequest]:
        """Approved bookings of one venue that touch ``start_date``..``end_date``."""

        matching = [
            item
            for item in self._items
            if item.venue_id == venue_id
            and item.status is BookingRequestStatus.APPROVED
            and item.start_date <= end_date
            and item.end_date >= start_date
        ]
        return sorted(matching, key=lambda item: item.created_at)

    def clear(self) -> None:
        self._items.clear()


# Module-level singleton used when VENUE_STORAGE_BACKEND=memory.
booking_repository = BookingRequestRepository()


@lru_cache
def _supabase_booking_repository() -> BookingRequestStore:
    from app.supabase_booking_repository import SupabaseBookingRepository

    settings = get_settings()
    return SupabaseBookingRepository(
        str(settings.supabase_url),
        settings.supabase_secret_key.get_secret_value(),
    )


def get_booking_repository() -> BookingRequestStore:
    """FastAPI dependency returning the configured booking-request store."""

    if get_settings().venue_storage_backend == "supabase":
        return _supabase_booking_repository()
    return booking_repository
