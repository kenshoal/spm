"""Booking-request store backed by the Supabase ``venue_booking_requests`` table.

Same approach as ``SupabaseVenueRepository``: Supabase's Data API (PostgREST)
with the server-side secret key, implementing the interface of the in-memory
``BookingRequestRepository``. Schema:
``database/migrations/0018_venue_booking_requests.sql``.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import (
    BookingNotCancellableError,
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

    def create(self, booking: BookingRequest) -> BookingRequest:
        rows = self._request(
            "POST",
            # A new request is pending, so the cancel columns (migration 0042) are
            # left out: submitting then works before and after that migration.
            json=booking.model_dump(
                mode="json", exclude={"cancelled_by", "cancelled_at"}
            ),
            headers={"Prefer": "return=representation"},
        )
        if not rows:
            raise SupabaseRepositoryError("Venue store returned no row")
        return BookingRequest.model_validate(rows[0])

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
