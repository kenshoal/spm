"""Booking-request store backed by the Supabase ``venue_booking_requests`` table.

Same approach as ``SupabaseVenueRepository``: Supabase's Data API (PostgREST)
with the server-side secret key, implementing the interface of the in-memory
``BookingRequestRepository``. Schema:
``database/migrations/0018_venue_booking_requests.sql``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import (
    BookingEventChangedError,
    BookingEventNotFoundError,
    BookingNotCancellableError,
    BookingReplacementRefusedError,
    BookingRequestNotFoundError,
)
from app.supabase_repository import SupabaseRepositoryError, _is_uuid

TABLE = "venue_booking_requests"


class SupabaseBookingRepository:
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

    def _request(self, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            response = self._client.request(method, f"/{TABLE}", **kwargs)
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError("Venue store unavailable") from error
        if not response.is_success:
            raise SupabaseRepositoryError(
                f"Venue store request failed ({response.status_code})"
            )
        body = response.json() if response.content else []
        if not isinstance(body, list):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return body

    def create(
        self, booking: BookingRequest, *, expected_event_updated_at: datetime,
    ) -> BookingRequest:
        """Create through the version/assignment gate; never fall back to INSERT."""
        if not isinstance(expected_event_updated_at, datetime) or expected_event_updated_at.utcoffset() is None:
            raise SupabaseRepositoryError("Venue store unavailable")
        try:
            response = self._client.post(
                "/rpc/create_event_venue_booking_request",
                json={
                    "p_booking": booking.model_dump(mode="json"),
                    "p_expected_event_updated_at": expected_event_updated_at.isoformat(),
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError("Venue store unavailable") from error
        try:
            body = response.json()
        except ValueError as error:
            raise SupabaseRepositoryError("Venue store returned an unexpected response") from error
        if not response.is_success:
            code = body.get("code") if isinstance(body, dict) else None
            if code in {"P0002", "P0003"}:
                raise BookingEventNotFoundError
            if code == "P0004":
                raise BookingEventChangedError
            raise SupabaseRepositoryError("Venue store unavailable")
        if not isinstance(body, dict):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return BookingRequest.model_validate(body)

    def get(self, booking_id: str) -> BookingRequest | None:
        # Postgres rejects a malformed uuid literal; an unknown id is simply absent.
        if not _is_uuid(booking_id):
            return None
        rows = self._request(
            "GET", params={"id": f"eq.{booking_id}", "select": "*", "limit": "1"}
        )
        return BookingRequest.model_validate(rows[0]) if rows else None

    def list_by_status(
        self, status: BookingRequestStatus | str
    ) -> list[BookingRequest]:
        rows = self._request(
            "GET",
            params={
                "status": f"eq.{BookingRequestStatus(status).value}",
                "select": "*",
                "order": "created_at.asc,id.asc",
            },
        )
        return [BookingRequest.model_validate(row) for row in rows]

    def list_for_requester(self, user_id: str) -> list[BookingRequest]:
        if not _is_uuid(user_id):
            return []
        rows = self._request(
            "GET",
            params={
                "requested_by": f"eq.{user_id}",
                "select": "*",
                "order": "created_at.desc,id.desc",
            },
        )
        return [BookingRequest.model_validate(row) for row in rows]

    def list_for_event(self, event_request_id: str) -> list[BookingRequest]:
        if not _is_uuid(event_request_id):
            return []
        rows = self._request(
            "GET",
            params={
                "event_request_id": f"eq.{event_request_id}",
                "select": "*",
                "order": "created_at.asc,id.asc",
            },
        )
        return [BookingRequest.model_validate(row) for row in rows]

    def cancel(self, booking_id: str, cancelled_by: str) -> BookingRequest:
        """Cancel through ``cancel_venue_booking_request`` (migration 0042)."""

        # Postgres rejects a malformed uuid literal; an unknown id is simply absent.
        if not _is_uuid(booking_id):
            raise BookingRequestNotFoundError
        try:
            response = self._client.post(
                "/rpc/cancel_venue_booking_request",
                json={
                    "p_booking_request_id": booking_id,
                    "p_cancelled_by": cancelled_by,
                },
            )
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError("Venue store unavailable") from error
        if not response.is_success:
            try:
                code = response.json().get("code")
            except (ValueError, AttributeError):
                code = None
            if code == "P0002":
                raise BookingRequestNotFoundError
            if code == "55000":
                raise BookingNotCancellableError
            raise SupabaseRepositoryError(
                f"Venue store request failed ({response.status_code})"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return BookingRequest.model_validate(body)

    def list_approved_for_venue(
        self, venue_id: str, start_date: date, end_date: date
    ) -> list[BookingRequest]:
        """Approved bookings of one venue that touch ``start_date``..``end_date``."""

        if not _is_uuid(venue_id):
            return []
        rows = self._request(
            "GET",
            params={
                "venue_id": f"eq.{venue_id}",
                "status": "eq.approved",
                "start_date": f"lte.{end_date.isoformat()}",
                "end_date": f"gte.{start_date.isoformat()}",
                "select": "*",
            },
        )
        return [BookingRequest.model_validate(row) for row in rows]

    def create_replacement(
        self,
        replaces_booking_id: str,
        booking: BookingRequest,
        *,
        expected_event_updated_at: datetime,
    ) -> BookingRequest:
        """Create a replacement through ``create_replacement_venue_booking_request`` (0068).

        The function takes the dates, times and event from the replaced booking and
        the event metadata from the locked event row; only the new id, venue and
        requester come from here."""

        if not _is_uuid(replaces_booking_id):
            raise BookingRequestNotFoundError
        if (
            not isinstance(expected_event_updated_at, datetime)
            or expected_event_updated_at.utcoffset() is None
        ):
            raise SupabaseRepositoryError("Venue store unavailable")
        try:
            response = self._client.post(
                "/rpc/create_replacement_venue_booking_request",
                json={
                    "p_replaces_booking_id": replaces_booking_id,
                    "p_new_id": booking.id,
                    "p_venue_id": booking.venue_id,
                    "p_requested_by": booking.requested_by,
                    "p_expected_event_updated_at": expected_event_updated_at.isoformat(),
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError("Venue store unavailable") from error
        try:
            body = response.json()
        except ValueError as error:
            raise SupabaseRepositoryError("Venue store returned an unexpected response") from error
        if not response.is_success:
            code = body.get("code") if isinstance(body, dict) else None
            message = str(body.get("message", "")) if isinstance(body, dict) else ""
            if code == "P0002":
                if "Venue" in message:
                    raise BookingEventNotFoundError
                raise BookingRequestNotFoundError
            if code == "P0003":
                raise BookingEventNotFoundError
            if code == "P0004":
                if "not approved" in message:
                    raise BookingReplacementRefusedError("not_approved")
                if "not flagged" in message:
                    raise BookingReplacementRefusedError("not_flagged")
                raise BookingEventChangedError
            if code == "22023":
                raise BookingReplacementRefusedError("same_venue")
            if code == "23505":
                raise BookingReplacementRefusedError("replacement_exists")
            raise SupabaseRepositoryError("Venue store unavailable")
        if not isinstance(body, dict):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return BookingRequest.model_validate(body)

    def mark_needs_new_venue(self, booking_id: str) -> None:
        """Nothing to do: ``create_venue_block`` flags affected bookings (0064)."""
