"""eventRequestService seam for SCRUM-33 (contract stub, Leg 1).

equipmentService does not read eventRequestService's tables. To learn whether
the caller coordinates an event, it asks eventRequestService with the
caller's own token, as venueService does for SCRUM-32:

1. ``GET /event-requests/{id}/coordinator`` and compare ``coordinator_id``
   with the caller (a 200 alone is not proof: organisers also receive it);
2. on record only, ``GET /event-requests/{id}`` for the status and snapshot.

The transport is injectable so tests can fake eventRequestService without
touching the ``httpx.get`` stub that conftest.py uses for authService.

Leg 1 stub: the signatures are the agreed contract; behaviour arrives in
Leg 2 (docs/superpowers/plans/2026-10-06-scrum-33-equipment-requirements.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

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

    def assert_assigned(
        self, event_request_id: str, token: str, coordinator_id: str
    ) -> None:
        """Return if ``coordinator_id`` is the event's current Coordinator.

        Raises 404 (not assigned, no assignment, unknown event), 401 (invalid
        session) or 502 (unavailable or malformed reply).
        """
        raise NotImplementedError("SCRUM-33 Leg 2")

    def snapshot_for_coordinator(
        self, event_request_id: str, token: str, coordinator_id: str
    ) -> EventSnapshot:
        """``assert_assigned``, then read the event's status and snapshot."""
        raise NotImplementedError("SCRUM-33 Leg 2")


def get_event_request_client() -> EventRequestClient:
    """FastAPI dependency; the base URL comes from Settings
    (``EVENT_REQUEST_SERVICE_URL``). An invalid setting is a 503."""
    raise NotImplementedError("SCRUM-33 Leg 2")
