"""Venue store backed by the Supabase ``public.venues`` table.

Talks to Supabase's Data API (PostgREST) with the server-side secret key, and
implements the same interface as the in-memory ``VenueRepository`` so the
routers do not change. Schema: ``database/migrations/0016_venues.sql``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.models import Venue, VenueCreate, VenueUpdate, _now

TABLE = "venues"


class SupabaseRepositoryError(Exception):
    """The venue store could not be reached or returned an unexpected response."""


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


class SupabaseVenueRepository:
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

    def create(self, data: VenueCreate) -> Venue:
        venue = Venue(**data.model_dump())
        rows = self._request(
            "POST",
            json=venue.model_dump(mode="json"),
            headers={"Prefer": "return=representation"},
        )
        return Venue.model_validate(rows[0])

    def get(self, venue_id: str) -> Venue | None:
        # Postgres rejects a malformed uuid literal; an unknown id is simply absent.
        if not _is_uuid(venue_id):
            return None
        rows = self._request(
            "GET", params={"id": f"eq.{venue_id}", "select": "*", "limit": "1"}
        )
        return Venue.model_validate(rows[0]) if rows else None

    def list(self) -> list[Venue]:
        rows = self._request("GET", params={"select": "*", "order": "created_at.asc"})
        return [Venue.model_validate(row) for row in rows]

    def update(self, venue_id: str, data: VenueUpdate) -> Venue | None:
        if not _is_uuid(venue_id):
            return None
        patch = data.model_dump(mode="json", exclude_unset=True)
        patch["updated_at"] = _now().isoformat()
        rows = self._request(
            "PATCH",
            params={"id": f"eq.{venue_id}"},
            json=patch,
            headers={"Prefer": "return=representation"},
        )
        return Venue.model_validate(rows[0]) if rows else None

    def update_timing(
        self,
        venue_id: str,
        setup_minutes: int | None,
        turnaround_minutes: int | None,
        changed_by: str,
    ) -> Venue | None:
        """Change setup and/or turnaround through 0055's update_venue_timing, which
        saves the change record and flags affected bookings in the same transaction."""
        if not _is_uuid(venue_id):
            return None
        try:
            response = self._client.post(
                "/rpc/update_venue_timing",
                json={
                    "p_venue_id": venue_id,
                    "p_setup_minutes": setup_minutes,
                    "p_turnaround_minutes": turnaround_minutes,
                    "p_changed_by": changed_by,
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
                return None
            raise SupabaseRepositoryError(
                f"Venue store request failed ({response.status_code})"
            )
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("venue"), dict):
            raise SupabaseRepositoryError("Venue store returned an unexpected response")
        return Venue.model_validate(body["venue"])
