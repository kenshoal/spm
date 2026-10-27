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
from app.repositories.event_request_repository import SupabaseRepositoryError
from app.repositories.registration_repository import RegistrationRpcError

ATTENDEE_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

WAITING = "Waiting"
OFFERED = "Offered"
ACCEPTED = "Accepted"
WITHDRAWN = "Withdrawn"

OFFER_WINDOW = timedelta(hours=72)  # D1


class FakeWaitlistRepository(FakeRegistrationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, Any]] = []
        self._entry_clock = 0
        # AC4-N5: when set, the next write RPC fails like an unreachable Supabase.
        self.rpc_fails = False

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

    def withdraw(
        self, registration_id: str, attendee_id: str, now: Any
    ) -> dict[str, Any]:
        """SCRUM-22's withdrawal, then the same-transaction promotion (AC2-H1)."""
        row = super().withdraw(registration_id, attendee_id, now)
        self._promote(row["event_request_id"], now)
        return row

    def accept_waitlist_offer(
        self, entry_id: str, attendee_id: str, now: Any
    ) -> dict[str, Any]:
        """Mirrors `accept_waitlist_offer`: owner, Offered, D1 window."""
        if self.rpc_fails:
            raise SupabaseRepositoryError(
                "Supabase could not complete the acceptance"
            )
        entry = self._own_entry(entry_id, attendee_id)
        event = self.events.get(entry["event_request_id"])
        if event is None or event["status"] != "Confirmed":
            raise RegistrationRpcError("entry not found", "P0002", "entry not found")
        if entry["status"] != OFFERED:
            raise RegistrationRpcError("not offered", "P0004", "not offered")
        if now > entry["expires_at"]:
            raise RegistrationRpcError("offer expired", "P0004", "offer expired")
        self._clock += 1
        self.registrations.append(
            {
                "id": str(uuid4()),
                "event_request_id": entry["event_request_id"],
                "attendee_id": attendee_id,
                "status": "Registered",
                "created_at": now,
                "withdrawn_at": None,
            }
        )
        entry.update(
            status=ACCEPTED, offered_at=None, expires_at=None, place_id=None
        )
        return dict(entry)

    def withdraw_from_waitlist(
        self, entry_id: str, attendee_id: str, now: Any
    ) -> dict[str, Any]:
        """Mirrors `withdraw_from_waitlist`; an offer passes on (AC7)."""
        entry = self._own_entry(entry_id, attendee_id)
        if entry["status"] == WITHDRAWN:
            raise RegistrationRpcError(
                "already withdrawn", "P0004", "already withdrawn"
            )
        if entry["status"] == ACCEPTED:
            raise RegistrationRpcError("not offered", "P0004", "not offered")
        was_offered = entry["status"] == OFFERED
        entry.update(status=WITHDRAWN, withdrawn_at=now)
        if was_offered:
            self._promote(entry["event_request_id"], now)
        return dict(entry)

    def _own_entry(self, entry_id: str, attendee_id: str) -> dict[str, Any]:
        entry = next(
            (
                e
                for e in self.entries
                if e["id"] == entry_id and e["attendee_id"] == attendee_id
            ),
            None,
        )
        if entry is None:
            raise RegistrationRpcError("entry not found", "P0002", "entry not found")
        return entry

    def _promote(self, event_id: str, now: Any) -> None:
        """Offer the freed place to the earliest Waiting attendee (AC2)."""
        waiting = sorted(
            (
                e
                for e in self.entries
                if e["event_request_id"] == event_id and e["status"] == WAITING
            ),
            key=lambda e: (e["queued_at"], e["seq"]),
        )
        if not waiting:
            return
        waiting[0].update(
            status=OFFERED,
            offered_at=now,
            expires_at=now + OFFER_WINDOW,
            place_id=str(uuid4()),
        )

    def list_entries_for(self, attendee_id: str) -> list[dict[str, Any]]:
        """The caller's active entries, oldest first, with their positions.

        A position is the attendee's place in their event's Waiting queue
        (AC1-H3: the second joiner sees position 2; AC2-H1: once the first
        attendee is Offered, the next Waiting attendee is position 1). The
        offered holder is out of the queue and shows no position.
        """
        mine = [
            e
            for e in self.entries
            if e["attendee_id"] == attendee_id
            and e["status"] in (WAITING, OFFERED)
        ]
        mine.sort(key=lambda e: (e["queued_at"], e["seq"]))
        ranks: dict[str, int] = {}
        per_event: dict[str, int] = {}
        for entry in sorted(
            (e for e in self.entries if e["status"] == WAITING),
            key=lambda e: (e["queued_at"], e["seq"]),
        ):
            per_event[entry["event_request_id"]] = (
                per_event.get(entry["event_request_id"], 0) + 1
            )
            ranks[entry["id"]] = per_event[entry["event_request_id"]]
        return [dict(entry, position=ranks.get(entry["id"])) for entry in mine]


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
