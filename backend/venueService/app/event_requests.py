"""Client for the event facts venueService needs from eventRequestService.

A booking request must be tied to an event the caller currently coordinates.
eventRequestService owns event requests, so venueService asks it, using the
caller's own token: it answers a Coordinator only for events assigned to them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException, status

UNAVAILABLE = "Event request service unavailable"


@dataclass(frozen=True)
class EventSnapshot:
    event_name: str | None
    expected_attendance: int | None
    venue_requirements: str | None
    updated_at: datetime
    status: str | None = None
    accessibility_needs: str | None = None


class EventRequestClient:
    def __init__(
        self, base_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=10, transport=transport
        )

    def _get(self, path: str, token: str) -> dict[str, Any]:
        try:
            response = self._client.get(path, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE) from error
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
        if response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")
        if not response.is_success:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
        try:
            body = response.json()
        except ValueError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE) from error
        if not isinstance(body, dict):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
        return body

    def require_coordinator(
        self, event_request_id: str, token: str, coordinator_id: str
    ) -> None:
        """Raise unless ``coordinator_id`` is the event's current Coordinator.

        A 200 from ``GET /event-requests/{id}`` alone is not proof: the owning
        organiser receives it too. The assignment is the authority, and it is
        read again on every call so a reassignment takes effect at once.
        """

        assignment = self._get(f"/event-requests/{event_request_id}/coordinator", token)
        assigned = assignment.get("coordinator_id")
        if not isinstance(assigned, str):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE)
        if assigned != coordinator_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")

    def snapshot_for_coordinator(
        self, event_request_id: str, token: str, coordinator_id: str
    ) -> EventSnapshot:
        """Return the event's snapshot if ``coordinator_id`` is its Coordinator."""

        self.require_coordinator(event_request_id, token, coordinator_id)
        event = self._get(f"/event-requests/{event_request_id}", token)
        try:
            updated_at = datetime.fromisoformat(event["updated_at"])
            if updated_at.utcoffset() is None:
                raise ValueError("Event version must be timezone-aware")
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, UNAVAILABLE) from error
        return EventSnapshot(
            event_name=event.get("event_name"),
            expected_attendance=event.get("expected_attendance"),
            venue_requirements=event.get("venue_requirements"),
            updated_at=updated_at,
            status=event.get("status"),
            accessibility_needs=event.get("accessibility_needs"),
        )


def get_event_client() -> EventRequestClient:
    """FastAPI dependency; the base URL is read from the environment."""

    return EventRequestClient(
        os.getenv("EVENT_REQUEST_API_URL", "http://127.0.0.1:8003")
    )
