"""Shared fixtures for the SCRUM-21 API tests.

FakeRegistrationRepository mirrors what `register_for_event` does in the
database (lock, status, window, duplicate, capacity, insert) with its own small
implementation, so the API tests exercise the service's error mapping rather
than re-running the rules module they sit above.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.clock import get_now
from app.controllers import event_request_controller
from app.main import create_app
from app.repositories.registration_repository import RegistrationRpcError

NOW = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)
OPENS = NOW - timedelta(days=5)
CLOSES = NOW + timedelta(days=5)

ATTENDEE_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ATTENDEE_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

NON_CONFIRMED = [
    "Draft",
    "Submitted",
    "Under Review",
    "Changes Requested",
    "Rejected",
    "Approved",
    "Planning",
    "Completed",
    "Cancelled",
]

PUBLIC_KEYS = {
    "id",
    "event_name",
    "purpose",
    "description",
    "proposed_date_times",
    "registration_opens_at",
    "registration_closes_at",
    "registration_capacity",
    "places_remaining",
}


class FakeRegistrationRepository:
    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.registrations: list[dict[str, Any]] = []
        self._clock = 0

    # -- reads used by the service -------------------------------------
    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.events.get(event_id)
        return dict(row) if row else None

    def get_events(self, event_ids: list[str]) -> list[dict[str, Any]]:
        return [dict(self.events[i]) for i in event_ids if i in self.events]

    def list_confirmed_events(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.events.values() if r["status"] == "Confirmed"]

    def count_active(self, event_id: str) -> int:
        return self._stored_count(event_id)

    def _stored_count(self, event_id: str) -> int:
        """The table's real count; register uses this so a subclass can fake a stale read."""
        return sum(
            1
            for r in self.registrations
            if r["event_request_id"] == event_id and r["status"] == "Registered"
        )

    def count_active_for_events(self, event_ids: list[str]) -> dict[str, int]:
        return {i: self.count_active(i) for i in event_ids}

    def list_for_attendee(self, attendee_id: str) -> list[dict[str, Any]]:
        mine = [r for r in self.registrations if r["attendee_id"] == attendee_id]
        return [dict(r) for r in sorted(mine, key=lambda r: r["created_at"],
                                        reverse=True)]

    # -- the atomic write ---------------------------------------------
    def register(
        self, event_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        event = self.events.get(event_id)
        if event is None or event["status"] != "Confirmed":
            raise RegistrationRpcError("event not found", "P0002", "event not found")
        opens = event.get("registration_opens_at")
        closes = event.get("registration_closes_at")
        capacity = event.get("registration_capacity")
        if opens is None or closes is None or capacity is None or not (
            opens <= now < closes
        ):
            raise RegistrationRpcError(
                "registration not open", "P0004", "registration not open"
            )
        if any(
            r["event_request_id"] == event_id
            and r["attendee_id"] == attendee_id
            and r["status"] == "Registered"
            for r in self.registrations
        ):
            raise RegistrationRpcError(
                "already registered", "P0004", "already registered"
            )
        if self._stored_count(event_id) >= capacity:
            raise RegistrationRpcError("event full", "P0004", "event full")
        self._clock += 1
        row = {
            "id": str(uuid4()),
            "event_request_id": event_id,
            "attendee_id": attendee_id,
            "status": "Registered",
            "created_at": NOW + timedelta(seconds=self._clock),
        }
        self.registrations.append(row)
        return dict(row)


def add_event(
    repository: FakeRegistrationRepository, **overrides: Any
) -> str:
    event_id = str(uuid4())
    repository.events[event_id] = {
        "id": event_id,
        "organiser_id": "organiser-1",
        "status": "Confirmed",
        "event_name": "Community Dinner",
        "purpose": "Bring neighbours together",
        "description": "A shared meal",
        "proposed_date_times": [datetime(2030, 2, 1, 18, 0, tzinfo=UTC)],
        "expected_attendance": 40,
        "venue_requirements": "Hall with kitchen",
        "accessibility_needs": "Step-free access",
        "equipment_requirements": "Tables",
        "registration_needs": "Dietary notes",
        "registration_opens_at": OPENS,
        "registration_closes_at": CLOSES,
        "registration_capacity": 10,
        **overrides,
    }
    return event_id


def fill(
    repository: FakeRegistrationRepository, event_id: str, count: int
) -> None:
    """Give an event `count` active registrations by other attendees."""
    for _ in range(count):
        repository.registrations.append(
            {
                "id": str(uuid4()),
                "event_request_id": event_id,
                "attendee_id": str(uuid4()),
                "status": "Registered",
                "created_at": NOW - timedelta(days=1),
            }
        )


def make_client(
    repository: FakeRegistrationRepository | None = None,
    caller_id: str = ATTENDEE_A,
    roles: tuple[str, ...] = ("attendee",),
) -> TestClient:
    application = create_app(
        registration_repository=repository or FakeRegistrationRepository()
    )
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: event_request_controller.AuthenticatedCaller(
        id=caller_id, roles=roles
    )
    application.dependency_overrides[get_now] = lambda: NOW
    return TestClient(application)


def make_unauthenticated_client() -> TestClient:
    """Real auth dependency: a request without a header never reaches the service."""
    application = create_app(registration_repository=FakeRegistrationRepository())
    application.dependency_overrides[get_now] = lambda: NOW
    return TestClient(application)
