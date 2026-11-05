"""Booking-request stores and storage selection.

Same shape as ``app.repository``: the routers depend on ``BookingRequestStore``
and ``VENUE_STORAGE_BACKEND`` selects the in-memory store (default, tests) or
the Supabase store.
"""

from __future__ import annotations

from datetime import date, datetime
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


class BookingEventNotFoundError(Exception):
    """The event is absent or no longer assigned to the requesting coordinator."""


class BookingEventChangedError(Exception):
    """The event changed after the HTTP snapshot was read."""


class BookingReplacementRefusedError(Exception):
    """A booking cannot be replaced; ``reason`` names the rule (SCRUM-63 AC4)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BookingRequestStore(Protocol):
    def create(
        self, booking: BookingRequest, *, expected_event_updated_at: datetime,
    ) -> BookingRequest: ...
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
    def create_replacement(
        self,
        replaces_booking_id: str,
        booking: BookingRequest,
        *,
        expected_event_updated_at: datetime,
    ) -> BookingRequest: ...
    def mark_needs_new_venue(self, booking_id: str) -> None: ...


class BookingRequestRepository:
    """In-memory booking-request store."""

    def __init__(self) -> None:
        self._items: list[BookingRequest] = []
        # Bookings a venue block flagged as needing a new venue. In production the
        # database flags them in create_venue_block (0064); this mirrors it.
        self._flagged: set[str] = set()

    def create(
        self, booking: BookingRequest, *, expected_event_updated_at: datetime | None = None,
    ) -> BookingRequest:
        # Standalone memory storage retains direct seed calls. Shared version
        # and assignment guarantees belong to the Supabase transaction, not here.
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
        return matching

    def mark_needs_new_venue(self, booking_id: str) -> None:
        self._flagged.add(booking_id)

    def flagged_ids(self) -> set[str]:
        return set(self._flagged)

    def clear_flag(self, booking_id: str) -> None:
        self._flagged.discard(booking_id)

    def create_replacement(
        self,
        replaces_booking_id: str,
        booking: BookingRequest,
        *,
        expected_event_updated_at: datetime | None = None,
    ) -> BookingRequest:
        """Store a pending request that replaces a flagged, approved booking.

        The same rules as ``create_replacement_venue_booking_request`` (0068); the
        event version belongs to the Supabase transaction, not here."""

        with venue_write_lock:
            original = self.get(replaces_booking_id)
            if original is None:
                raise BookingRequestNotFoundError
            if original.status is not BookingRequestStatus.APPROVED:
                raise BookingReplacementRefusedError("not_approved")
            if original.venue_id == booking.venue_id:
                raise BookingReplacementRefusedError("same_venue")
            if replaces_booking_id not in self._flagged:
                raise BookingReplacementRefusedError("not_flagged")
            if any(
                item.replaces_booking_id == replaces_booking_id
                and item.status
                in (BookingRequestStatus.PENDING, BookingRequestStatus.APPROVED)
                for item in self._items
            ):
                raise BookingReplacementRefusedError("replacement_exists")
            booking.replaces_booking_id = replaces_booking_id
            self._items.append(booking)
            return booking.model_copy()

    def clear(self) -> None:
        self._items.clear()
        self._flagged.clear()


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
