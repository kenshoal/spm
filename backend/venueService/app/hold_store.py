"""Tentative venue hold stores (SCRUM-18).

``VENUE_STORAGE_BACKEND`` selects the store, as for venues and bookings:

* ``memory``: applies the hold rules in process memory, using the in-memory
  venue, block and booking stores. Used by the unit tests. The router checks the
  coordinator and the event status first; the memory store trusts it.
* ``supabase``: calls 0066's functions, which lock the venue and re-check the
  coordinator, the event status and every conflict in one transaction. Holds
  read for search, availability and the calendar leave out those of Cancelled
  or Rejected events, as the database guard does; memory storage has no events,
  so it cannot.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.availability_models import Period
from app.block_checks import check_availability
from app.block_repository import block_repository
from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import BookingEventChangedError, booking_repository
from app.config import get_settings
from app.hold_models import HoldNotice, HoldPlacement, HoldStatus, VenueHold
from app.models import Venue
from app.repository import repository
from app.supabase_repository import SupabaseRepositoryError, _is_uuid
from app.venue_locks import venue_write_lock

EXPIRING_NOTICE = timedelta(hours=24)


class HoldNotFoundError(Exception):
    """The hold, its venue or its event does not exist."""


class HoldForbiddenError(Exception):
    """The caller is not the event's assigned coordinator."""


class HoldEventClosedError(Exception):
    """The event cannot hold a venue in its current status."""


class HoldNotActiveError(Exception):
    """The hold has ended or expired, or its conversion is still pending."""


class VenueHoldStore(Protocol):
    def place(
        self, venue: Venue, event_request_id: str, period: Period,
        expires_at: datetime, placed_by: str,
    ) -> HoldPlacement: ...
    def get(self, hold_id: str) -> VenueHold | None: ...
    def list_for_event(self, event_request_id: str) -> list[VenueHold]: ...
    def list_for_venue(self, venue_id: str, start_date: date, end_date: date) -> list[VenueHold]: ...
    def release(self, hold_id: str, released_by: str) -> VenueHold: ...
    def convert(
        self, hold_id: str, booking: BookingRequest, expected_event_updated_at: datetime,
    ) -> tuple[VenueHold, BookingRequest]: ...
    def sweep(self, as_of: datetime) -> list[HoldNotice]: ...
    def mark_notice(self, hold_id: str, kind: str) -> None: ...


class MemoryHoldStore:
    """Holds in process memory, checked against the in-memory venue stores."""

    def __init__(self) -> None:
        self._holds: dict[str, VenueHold] = {}
        self._notified: set[tuple[str, str]] = set()

    def place(
        self, venue: Venue, event_request_id: str, period: Period,
        expires_at: datetime, placed_by: str,
    ) -> HoldPlacement:
        with venue_write_lock:
            return self._place(venue, event_request_id, period, expires_at, placed_by)

    def _place(
        self, venue: Venue, event_request_id: str, period: Period,
        expires_at: datetime, placed_by: str,
    ) -> HoldPlacement:
        result = check_availability(
            venue,
            period,
            block_repository.list_for_venue(venue.id),
            booking_repository.list_by_status(BookingRequestStatus.APPROVED),
            self._holds.values(),
        )
        if result.reasons:
            return HoldPlacement(
                refusal_codes=result.reasons,
                conflicting_block_ids=sorted({c.block_id for c in result.conflicts}),
                conflicting_booking_ids=[c.booking_id for c in result.booking_conflicts],
                conflicting_hold_ids=[c.hold_id for c in result.hold_conflicts],
            )
        hold = VenueHold(
            venue_id=venue.id,
            event_request_id=event_request_id,
            start_date=period.start_date,
            end_date=period.end_date,
            start_minute=period.start_minute,
            end_minute=period.end_minute,
            expires_at=expires_at,
            placed_by=placed_by,
        )
        self._holds[hold.id] = hold
        return HoldPlacement(hold=hold.model_copy())

    def get(self, hold_id: str) -> VenueHold | None:
        hold = self._holds.get(hold_id)
        return hold.model_copy() if hold else None

    def list_for_event(self, event_request_id: str) -> list[VenueHold]:
        return sorted(
            (h.model_copy() for h in self._holds.values() if h.event_request_id == event_request_id),
            key=lambda h: h.placed_at,
        )

    def list_for_venue(self, venue_id: str, start_date: date, end_date: date) -> list[VenueHold]:
        return [
            h.model_copy()
            for h in self._holds.values()
            if h.venue_id == venue_id and h.status is HoldStatus.ACTIVE
            and h.start_date <= end_date and h.end_date >= start_date
        ]

    def _active(self, hold_id: str) -> VenueHold:
        hold = self._holds.get(hold_id)
        if hold is None:
            raise HoldNotFoundError
        if not hold.protects(datetime.now(UTC)):
            raise HoldNotActiveError
        return hold

    def release(self, hold_id: str, released_by: str) -> VenueHold:
        hold = self._active(hold_id)
        hold.status, hold.closed_at, hold.closed_by = (
            HoldStatus.RELEASED, datetime.now(UTC), released_by,
        )
        return hold.model_copy()

    def convert(
        self, hold_id: str, booking: BookingRequest, expected_event_updated_at: datetime,
    ) -> tuple[VenueHold, BookingRequest]:
        hold = self._active(hold_id)
        linked = booking_repository.get(hold.booking_request_id) if hold.booking_request_id else None
        if linked is not None and linked.status is BookingRequestStatus.PENDING:
            raise HoldNotActiveError
        created = booking_repository.create(
            booking.model_copy(update={
                "venue_id": hold.venue_id,
                "event_request_id": hold.event_request_id,
                "start_date": hold.start_date,
                "end_date": hold.end_date,
                "start_minute": hold.start_minute,
                "end_minute": hold.end_minute,
                "status": BookingRequestStatus.PENDING,
            }),
            expected_event_updated_at=expected_event_updated_at,
        )
        hold.booking_request_id = created.id
        return hold.model_copy(), created

    def close_for_decision(self, booking: BookingRequest, decided_by: str) -> None:
        """End the hold a decided request was converted from (0066 does this in SQL).
        An expired hold is left to the sweep, which marks it expired and sends its notice."""
        status = (
            HoldStatus.CONVERTED if booking.status is BookingRequestStatus.APPROVED
            else HoldStatus.RELEASED
        )
        now = datetime.now(UTC)
        for hold in self._holds.values():
            if hold.booking_request_id == booking.id and hold.protects(now):
                hold.status, hold.closed_at, hold.closed_by = status, now, decided_by

    def protecting(self, venue_id: str, exclude_event_id: str | None = None) -> list[VenueHold]:
        """Holds at the venue that still protect their time, except those of the
        given event: a hold never blocks its own event's bookings (0066)."""
        now = datetime.now(UTC)
        return [
            h for h in self._holds.values()
            if h.venue_id == venue_id and h.protects(now) and h.event_request_id != exclude_event_id
        ]

    def sweep(self, as_of: datetime) -> list[HoldNotice]:
        notices = []
        for hold in sorted(self._holds.values(), key=lambda h: (h.expires_at, h.id)):
            if hold.status is HoldStatus.ACTIVE and hold.expires_at <= as_of:
                hold.status, hold.closed_at = HoldStatus.EXPIRED, hold.expires_at
            if (
                hold.status is HoldStatus.ACTIVE
                and (hold.id, "expiring") not in self._notified
                and hold.expires_at - EXPIRING_NOTICE <= as_of < hold.expires_at
            ):
                notices.append(self._notice(hold, "expiring"))
            if hold.status is HoldStatus.EXPIRED and (hold.id, "expired") not in self._notified:
                notices.append(self._notice(hold, "expired"))
        return notices

    def _notice(self, hold: VenueHold, kind: str) -> HoldNotice:
        venue = repository.get(hold.venue_id)
        return HoldNotice(
            hold_id=hold.id,
            kind=kind,
            # Memory storage has no assignments; the coordinator who placed it.
            recipient_id=hold.placed_by,
            venue_id=hold.venue_id,
            venue_name=venue.name if venue else None,
            event_request_id=hold.event_request_id,
            start_date=hold.start_date,
            end_date=hold.end_date,
            start_minute=hold.start_minute,
            end_minute=hold.end_minute,
            expires_at=hold.expires_at,
        )

    def mark_notice(self, hold_id: str, kind: str) -> None:
        self._notified.add((hold_id, kind))

    def add(self, hold: VenueHold) -> VenueHold:
        """Store a hold as given, for tests that need a past expiry."""
        self._holds[hold.id] = hold
        return hold

    def clear(self) -> None:
        self._holds.clear()
        self._notified.clear()


class SupabaseHoldStore:
    """Calls 0066's hold functions through Supabase's Data API."""

    def __init__(
        self, url: str, secret_key: str, transport: httpx.BaseTransport | None = None,
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
        errors = {
            "P0002": HoldNotFoundError,
            "P0003": HoldForbiddenError,
            "55000": HoldNotActiveError,
        }
        if code in errors:
            raise errors[code]
        if code == "P0004":
            raise HoldEventClosedError
        raise SupabaseRepositoryError(f"Venue store request failed ({response.status_code})")

    def _rows(self, params: dict[str, str]) -> list[VenueHold]:
        rows = self._send("GET", "/venue_holds", params={"select": "*"} | params)
        if not isinstance(rows, list):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return [VenueHold.model_validate(row) for row in rows]

    def place(
        self, venue: Venue, event_request_id: str, period: Period,
        expires_at: datetime, placed_by: str,
    ) -> HoldPlacement:
        body = self._send("POST", "/rpc/place_venue_hold", json={
            "p_venue_id": venue.id,
            "p_event_request_id": event_request_id,
            "p_start_date": period.start_date.isoformat(),
            "p_end_date": period.end_date.isoformat(),
            "p_start_minute": period.start_minute,
            "p_end_minute": period.end_minute,
            "p_expires_at": expires_at.isoformat(),
            "p_placed_by": placed_by,
        })
        if not isinstance(body, dict) or body.get("outcome") not in ("placed", "refused"):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        if body["outcome"] == "placed":
            return HoldPlacement(hold=VenueHold.model_validate(body["hold"]))
        return HoldPlacement.model_validate({k: v for k, v in body.items() if k != "outcome"})

    def get(self, hold_id: str) -> VenueHold | None:
        if not _is_uuid(hold_id):
            return None
        rows = self._rows({"id": f"eq.{hold_id}"})
        return rows[0] if rows else None

    def list_for_event(self, event_request_id: str) -> list[VenueHold]:
        if not _is_uuid(event_request_id):
            return []
        return self._rows({
            "event_request_id": f"eq.{event_request_id}", "order": "placed_at.asc,id.asc",
        })

    def list_for_venue(self, venue_id: str, start_date: date, end_date: date) -> list[VenueHold]:
        if not _is_uuid(venue_id):
            return []
        return self._rows({
            # Holds of Cancelled or Rejected events stop protecting at once (0066).
            "select": "*,event_requests!inner(status)",
            "event_requests.status": "not.in.(Cancelled,Rejected)",
            "venue_id": f"eq.{venue_id}",
            "status": "eq.active",
            "start_date": f"lte.{end_date.isoformat()}",
            "end_date": f"gte.{start_date.isoformat()}",
        })

    def release(self, hold_id: str, released_by: str) -> VenueHold:
        if not _is_uuid(hold_id):
            raise HoldNotFoundError
        body = self._send("POST", "/rpc/release_venue_hold", json={
            "p_hold_id": hold_id, "p_released_by": released_by,
        })
        return VenueHold.model_validate(body)

    def convert(
        self, hold_id: str, booking: BookingRequest, expected_event_updated_at: datetime,
    ) -> tuple[VenueHold, BookingRequest]:
        if not _is_uuid(hold_id):
            raise HoldNotFoundError
        try:
            body = self._send("POST", "/rpc/convert_venue_hold", json={
                "p_hold_id": hold_id,
                "p_booking": {
                    "id": booking.id,
                    "requested_by": booking.requested_by,
                    "created_at": booking.created_at.isoformat(),
                },
                "p_expected_event_updated_at": expected_event_updated_at.isoformat(),
            })
        except HoldEventClosedError as error:
            # 0056 raises P0004 when the event changed since the caller read it.
            raise BookingEventChangedError from error
        if not isinstance(body, dict):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return VenueHold.model_validate(body["hold"]), BookingRequest.model_validate(body["booking"])

    def sweep(self, as_of: datetime) -> list[HoldNotice]:
        body = self._send("POST", "/rpc/sweep_venue_holds", json={"p_as_of": as_of.isoformat()})
        if not isinstance(body, list):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return [HoldNotice.model_validate(item) for item in body]

    def mark_notice(self, hold_id: str, kind: str) -> None:
        self._send("POST", "/rpc/mark_venue_hold_notice", json={"p_hold_id": hold_id, "p_kind": kind})


# Module-level singleton used when VENUE_STORAGE_BACKEND=memory.
memory_hold_store = MemoryHoldStore()


@lru_cache
def _supabase_hold_store() -> VenueHoldStore:
    settings = get_settings()
    return SupabaseHoldStore(
        str(settings.supabase_url), settings.supabase_secret_key.get_secret_value(),
    )


def get_hold_store() -> VenueHoldStore:
    """FastAPI dependency returning the configured hold store."""

    if get_settings().venue_storage_backend == "supabase":
        return _supabase_hold_store()
    return memory_hold_store

