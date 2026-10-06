"""eventRequestService seam for SCRUM-33.

equipmentService does not read eventRequestService's tables. To learn whether
the caller coordinates an event, it asks eventRequestService with the
caller's own token, as venueService does for SCRUM-32:

1. ``GET /event-requests/{id}/coordinator`` and compare ``coordinator_id``
   with the caller (a 200 alone is not proof: organisers also receive it);
2. on record only, ``GET /event-requests/{id}`` for the status and snapshot.

The transport is injectable so tests can fake eventRequestService without
touching the ``httpx.get`` stub that conftest.py uses for authService.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.config import get_settings

UNAVAILABLE = "Event request service unavailable"
NOT_FOUND = "Event request not found"


@dataclass(frozen=True)
class EventSnapshot:
    """What a requirement copies from its event when it is recorded."""

    status: str
    event_name: str | None
    proposed_date_times: list[str] = field(default_factory=list)


class EventRequestClient:
    def __init__(
        self, base_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=10, transport=transport
        )

    def _get(self, path: str, token: str) -> dict[str, Any]:
        try:
            response = self._client.get(
                path, headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE) from error
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
        # 403 is the owning organiser's (or anyone unauthorised's) answer; it
        # must be indistinguishable from a missing event.
        if response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        if not response.is_success:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
        try:
            body = response.json()
        except ValueError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE) from error
        if not isinstance(body, dict):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
        return body

    def assert_assigned(
        self, event_request_id: str, token: str, coordinator_id: str
    ) -> None:
        """Return if ``coordinator_id`` is the event's current Coordinator.

        Raises 404 (not assigned, no assignment, unknown event), 401 (invalid
        session) or 502 (unavailable or malformed reply).
        """
        assignment = self._get(f"/event-requests/{event_request_id}/coordinator", token)
        assigned = assignment.get("coordinator_id")
        if not isinstance(assigned, str):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
        if assigned != coordinator_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    def snapshot_for_coordinator(
        self, event_request_id: str, token: str, coordinator_id: str
    ) -> EventSnapshot:
        """``assert_assigned``, then read the event's status and snapshot."""
        self.assert_assigned(event_request_id, token, coordinator_id)
        event = self._get(f"/event-requests/{event_request_id}", token)
        event_status = event.get("status")
        if not isinstance(event_status, str):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
        proposed = event.get("proposed_date_times")
        return EventSnapshot(
            status=event_status,
            event_name=event.get("event_name"),
            proposed_date_times=(
                [str(moment) for moment in proposed]
                if isinstance(proposed, list)
                else []
            ),
        )


def get_event_request_client() -> EventRequestClient:
    """FastAPI dependency; the base URL comes from Settings
    (``EVENT_REQUEST_SERVICE_URL``). An invalid setting is a 503."""
    try:
        base_url = str(get_settings().event_request_service_url).rstrip("/")
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Service is not configured"
        ) from error
    return EventRequestClient(base_url)
