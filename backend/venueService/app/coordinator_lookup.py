"""Find the current assigned Coordinator of an event request (SCRUM-23 AC7, SCRUM-63 AC5).

A block notice and the decision on a replacement booking go to the Coordinator who
holds the event now, not to whoever made the booking: after a reassignment that is a
former Coordinator, who must not be told. venueService cannot ask eventRequestService
(it answers with the caller's token and Venue Staff may not read an event), so, like
``organiser_lookup``, this reads the shared database with the service key, and only the
latest assignment row. An event with no assignment gives ``None``; an unreachable store
raises ``CoordinatorLookupError``, which the caller treats as "do not notify".
"""

from __future__ import annotations

import logging
from functools import lru_cache

import httpx

from app.booking_models import BookingRequest
from app.config import get_settings
from app.supabase_repository import _is_uuid

logger = logging.getLogger(__name__)


class CoordinatorLookupError(Exception):
    """The assignment store could not be asked."""


class CoordinatorLookup:
    """Without Supabase (local, in-memory) there are no assignments to ask."""

    def coordinator_of(self, event_request_id: str) -> str | None:
        return None


class SupabaseCoordinatorLookup(CoordinatorLookup):
    def __init__(
        self, url: str, secret_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={"apikey": secret_key, "Authorization": f"Bearer {secret_key}"},
            timeout=5,
            transport=transport,
        )

    def coordinator_of(self, event_request_id: str) -> str | None:
        # Postgres rejects a malformed uuid literal; an unknown id is simply absent.
        if not _is_uuid(event_request_id):
            return None
        try:
            response = self._client.get(
                "/event_coordinator_assignments",
                params={
                    "event_request_id": f"eq.{event_request_id}",
                    "select": "coordinator_id",
                    # The latest row is the current assignment; ids only grow.
                    "order": "id.desc",
                    "limit": "1",
                },
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise CoordinatorLookupError("Assignment store unavailable") from error
        if not isinstance(rows, list) or not rows:
            return None
        coordinator_id = rows[0].get("coordinator_id") if isinstance(rows[0], dict) else None
        return coordinator_id if isinstance(coordinator_id, str) else None


def notice_recipient(booking: BookingRequest, coordinators: CoordinatorLookup) -> str | None:
    """Who is told about ``booking``: the event's current Coordinator.

    With no assignment on record (a local run, or an event without one) the Coordinator who
    made the booking is told. If the assignment store cannot be asked nobody is: a former
    Coordinator must not be told, and the saved block or decision stands either way.
    """
    try:
        current = coordinators.coordinator_of(booking.event_request_id)
    except CoordinatorLookupError:
        logger.warning(
            "Could not find the current Coordinator of event request %s to notify of booking %s",
            booking.event_request_id,
            booking.id,
        )
        return None
    return current or booking.requested_by


@lru_cache
def _supabase_coordinator_lookup() -> CoordinatorLookup:
    settings = get_settings()
    return SupabaseCoordinatorLookup(
        str(settings.supabase_url), settings.supabase_secret_key.get_secret_value()
    )


def get_coordinator_lookup() -> CoordinatorLookup:
    """FastAPI dependency returning the configured lookup."""

    if get_settings().venue_storage_backend == "supabase":
        return _supabase_coordinator_lookup()
    return CoordinatorLookup()
