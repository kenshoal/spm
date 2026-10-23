"""Find the Organiser of an event request (SCRUM-36 AC2).

venueService cannot ask eventRequestService: that service answers with the
caller's token, and Venue Staff may not read an event. So, like the booking
store, this reads the shared database with the service key, and only the one
column it needs. An unknown event gives ``None``; an unreachable store raises
``OrganiserLookupError``, which the caller treats as "do not notify".
"""

from __future__ import annotations

from functools import lru_cache

import httpx

from app.config import get_settings
from app.supabase_repository import _is_uuid


class OrganiserLookupError(Exception):
    """The event store could not be asked."""


class OrganiserLookup:
    """Without Supabase (local, in-memory) there are no event requests to ask."""

    def organiser_of(self, event_request_id: str) -> str | None:
        return None


class SupabaseOrganiserLookup(OrganiserLookup):
    def __init__(
        self, url: str, secret_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={"apikey": secret_key, "Authorization": f"Bearer {secret_key}"},
            timeout=5,
            transport=transport,
        )

    def organiser_of(self, event_request_id: str) -> str | None:
        # Postgres rejects a malformed uuid literal; an unknown id is simply absent.
        if not _is_uuid(event_request_id):
            return None
        try:
            response = self._client.get(
                "/event_requests",
                params={"id": f"eq.{event_request_id}", "select": "organiser_id"},
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OrganiserLookupError("Event store unavailable") from error
        if not isinstance(rows, list) or not rows:
            return None
        organiser_id = rows[0].get("organiser_id") if isinstance(rows[0], dict) else None
        return organiser_id if isinstance(organiser_id, str) else None


@lru_cache
def _supabase_organiser_lookup() -> OrganiserLookup:
    settings = get_settings()
    return SupabaseOrganiserLookup(
        str(settings.supabase_url), settings.supabase_secret_key.get_secret_value()
    )


def get_organiser_lookup() -> OrganiserLookup:
    """FastAPI dependency returning the configured lookup."""

    if get_settings().venue_storage_backend == "supabase":
        return _supabase_organiser_lookup()
    return OrganiserLookup()
