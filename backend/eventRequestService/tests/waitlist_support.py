"""Shared fixtures for the SCRUM-24 API tests.

FakeWaitlistRepository extends the SCRUM-21 fake with the waiting-list rows and
mirrors what `join_waitlist` will enforce in the database (SCRUM-24 D10), so
the API tests exercise the service's error mapping rather than re-running the
rules module they sit above. The real database function is proven by
database/verify_event_waitlist.sql.
"""

from datetime import timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from registration_support import (
    ATTENDEE_A,
    NOW,
    FakeRegistrationRepository,
)

from app.clock import get_now
from app.controllers import event_request_controller
from app.main import create_app
from app.repositories.registration_repository import RegistrationRpcError

ATTENDEE_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

WAITING = "Waiting"
OFFERED = "Offered"

OFFER_WINDOW = timedelta(hours=72)  # D1


class FakeWaitlistRepository(FakeRegistrationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, Any]] = []
        self._entry_clock = 0

    def active_entry(
        self, event_id: str, attendee_id: str
    ) -> dict[str, Any] | None:
        return next(
            (
                dict(e)
                for e in self.entries
                if e["event_request_id"] == event_id
                and e["attendee_id"] == attendee_id
                and e["status"] in (WAITING, OFFERED)
            ),
            None,
        )

    def places_taken(self, event_id: str) -> int:
        """D6: Registered registrations plus pending offers."""
        offered = sum(
            1
            for e in self.entries
            if e["event_request_id"] == event_id and e["status"] == OFFERED
        )
        return self._stored_count(event_id) + offered

    def join_waitlist(
        self, event_id: str, attendee_id: str, now: Any
    ) -> dict[str, Any]:
        """Mirrors `join_waitlist`: visibility, window, duplicates, D6 capacity."""
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
        if self.has_active(event_id, attendee_id):
            raise RegistrationRpcError(
                "already registered", "P0004", "already registered"
            )
        if self.active_entry(event_id, attendee_id) is not None:
            raise RegistrationRpcError(
                "already waitlisted", "P0004", "already waitlisted"
            )
        if self.places_taken(event_id) < capacity:
            raise RegistrationRpcError("places available", "P0004", "places available")
        self._entry_clock += 1
        row = {
            "id": str(uuid4()),
            "seq": self._entry_clock,
            "event_request_id": event_id,
            "attendee_id": attendee_id,
            "status": WAITING,
            "queued_at": now,
            "offered_at": None,
            "expires_at": None,
            "place_id": None,
        }
        self.entries.append(row)
        return dict(row)

    def list_entries_for(self, attendee_id: str) -> list[dict[str, Any]]:
        """The caller's active entries, oldest first, with their positions."""
        mine = [
            e
            for e in self.entries
            if e["attendee_id"] == attendee_id
            and e["status"] in (WAITING, OFFERED)
        ]
        mine.sort(key=lambda e: (e["queued_at"], e["seq"]))
        positions: dict[str, int] = {}
        for entry in mine:
            previous = positions.get(entry["event_request_id"], 0)
            positions[entry["event_request_id"]] = previous + 1
            entry = dict(entry)
            entry["position"] = positions[entry["event_request_id"]]
        return mine


def add_waitlist_entry(
    repository: FakeWaitlistRepository,
    event_id: str,
    attendee_id: str,
    **overrides: Any,
) -> str:
    """Store one waiting-list entry directly and return its id."""
    repository._entry_clock += 1
    entry_id = str(uuid4())
    repository.entries.append(
        {
            "id": entry_id,
            "seq": repository._entry_clock,
            "event_request_id": event_id,
            "attendee_id": attendee_id,
            "status": WAITING,
            "queued_at": NOW,
            "offered_at": None,
            "expires_at": None,
            "place_id": None,
            **overrides,
        }
    )
    return entry_id


def add_offer(
    repository: FakeWaitlistRepository, event_id: str, attendee_id: str
) -> str:
    """Store one pending offer, so the place is held (D6)."""
    return add_waitlist_entry(
        repository,
        event_id,
        attendee_id,
        status=OFFERED,
        offered_at=NOW,
        expires_at=NOW + OFFER_WINDOW,
        place_id=str(uuid4()),
    )


def make_waitlist_client(
    repository: FakeWaitlistRepository | None = None,
    caller_id: str = ATTENDEE_A,
    roles: tuple[str, ...] = ("attendee",),
) -> TestClient:
    application = create_app(
        registration_repository=repository or FakeWaitlistRepository()
    )
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: event_request_controller.AuthenticatedCaller(
        id=caller_id, roles=roles
    )
    application.dependency_overrides[get_now] = lambda: NOW
    return TestClient(application)


def make_unauthenticated_waitlist_client() -> TestClient:
    """Real auth dependency: a request without a header never reaches the service."""
    application = create_app(registration_repository=FakeWaitlistRepository())
    application.dependency_overrides[get_now] = lambda: NOW
    return TestClient(application)
