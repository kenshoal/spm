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
from app.services.waitlist_rules import may_issue_offer

ATTENDEE_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

WAITING = "Waiting"
OFFERED = "Offered"
ACCEPTED = "Accepted"
WITHDRAWN = "Withdrawn"
CLOSED = "Closed"

WARNING_OFFSET = timedelta(hours=48)  # D2

OFFER_WINDOW = timedelta(hours=72)  # D1


def _epoch(moment: Any) -> int:
    """The DB keys use extract(epoch from ...); the fake mirrors the instants."""
    return int(moment.timestamp())


class FakeWaitlistRepository(FakeRegistrationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, Any]] = []
        self._entry_clock = 0
        # AC4-N5: when set, the next write RPC fails like an unreachable Supabase.
        self.rpc_fails = False
        # The notification outbox: notices written in the same "transaction"
        # as the change they belong to, delivered later by the relay.
        self.outbox: list[dict[str, Any]] = []
        # D7's per-place memory, as far as this fake needs it: attendees who
        # let a place lapse are never re-offered that place.
        self.place_lapsed: dict[str, set[str]] = {}

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
            "warned_at": None,
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
        place = entry["place_id"]
        entry.update(status=WITHDRAWN, withdrawn_at=now)
        if was_offered:
            self._promote(entry["event_request_id"], now, place_id=place)
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

    def _promote(self, event_id: str, now: Any, place_id: str | None = None) -> None:
        """Offer the freed place to the earliest eligible Waiting attendee (AC2, D7).

        An attendee who let this place lapse is skipped; if nobody is eligible
        the place simply stays free. The offer and its notice are written
        together, like the database's single transaction.
        """
        lapsed = self.place_lapsed.get(place_id or "", set())
        waiting = sorted(
            (
                e
                for e in self.entries
                if e["event_request_id"] == event_id
                and e["status"] == WAITING
                and e["attendee_id"] not in lapsed
            ),
            key=lambda e: (e["queued_at"], e["seq"]),
        )
        if not waiting:
            return
        chosen = waiting[0]
        place = place_id or str(uuid4())
        chosen.update(
            status=OFFERED,
            offered_at=now,
            expires_at=now + OFFER_WINDOW,
            place_id=place,
        )

        self._write_notice(
            chosen,
            "waitlist_offered",
            f"waitlist-offered:{chosen['id']}:{_epoch(now)}",
            {"event_request_id": event_id, "expires_at": chosen["expires_at"]},
            now,
        )

    def _write_notice(
        self,
        entry: dict[str, Any],
        event_type: str,
        key: str,
        payload: dict[str, Any],
        now: Any,
    ) -> None:
        self.outbox.append(
            {
                "id": str(uuid4()),
                "entry_id": entry["id"],
                "recipient_id": entry["attendee_id"],
                "event_type": event_type,
                "idempotency_key": key,
                "payload": dict(payload),
                "occurred_at": now,
                "published_at": None,
            }
        )

    def process_waitlist_timers(self, now: Any) -> int:
        """Mirrors `process_waitlist_timers` (SCRUM-24 D1-D3, D11, D12, D2).

        One pass per event with active entries: expiries strictly after
        expires_at with the hand-over in the same call (AC9-H1), the cut-off
        close, then the one 48h warning. Repeating a pass changes nothing.
        """
        if self.rpc_fails:
            raise SupabaseRepositoryError(
                "Supabase could not complete the timer pass"
            )
        touched = 0
        event_ids = sorted(
            {
                e["event_request_id"]
                for e in self.entries
                if e["status"] in (WAITING, OFFERED)
            }
        )
        for event_id in event_ids:
            event = self.events.get(event_id)
            if event is None or event["status"] != "Confirmed":
                continue
            dates = event.get("proposed_date_times") or []
            start = min(dates) if dates else None

            offered = sorted(
                (
                    e
                    for e in self.entries
                    if e["event_request_id"] == event_id
                    and e["status"] == OFFERED
                ),
                key=lambda e: (e["queued_at"], e["seq"]),
            )
            for entry in offered:
                if entry["expires_at"] is None or now <= entry["expires_at"]:
                    continue
                # D1: strictly after expires_at. D7: this place lapses for them.
                place = entry["place_id"]
                self.place_lapsed.setdefault(place, set()).add(entry["attendee_id"])
                self._write_notice(
                    entry,
                    "waitlist_offer_expired",
                    f"waitlist-expired:{entry['id']}:{_epoch(entry['offered_at'])}",
                    {"event_request_id": event_id},
                    now,
                )
                if start is not None and may_issue_offer(now, start):
                    # D3: to the back; the place passes on in this same pass (AC9-H1)
                    entry.update(
                        status=WAITING,
                        queued_at=now,
                        offered_at=None,
                        expires_at=None,
                        warned_at=None,
                        place_id=None,
                    )
                    self._promote(event_id, now, place_id=place)
                else:
                    # D11/D12: Closed instead of requeued; the place opens to
                    # normal registration
                    entry.update(
                        status=CLOSED,
                        closed_at=now,
                        offered_at=None,
                        expires_at=None,
                        warned_at=None,
                        place_id=None,
                    )
                    self._write_notice(
                        entry,
                        "waitlist_closed",
                        f"waitlist-closed:{entry['id']}:{_epoch(now)}",
                        {"event_request_id": event_id},
                        now,
                    )
                touched += 1

            if start is not None and now >= start - OFFER_WINDOW:
                for entry in [
                    e
                    for e in self.entries
                    if e["event_request_id"] == event_id
                    and e["status"] == WAITING
                ]:
                    entry.update(status=CLOSED, closed_at=now)
                    self._write_notice(
                        entry,
                        "waitlist_closed",
                        f"waitlist-closed:{entry['id']}:{_epoch(now)}",
                        {"event_request_id": event_id},
                        now,
                    )
                    touched += 1

            for entry in [
                e
                for e in self.entries
                if e["event_request_id"] == event_id
                and e["status"] == OFFERED
                and e["warned_at"] is None
                and e["offered_at"] is not None
                and now >= e["offered_at"] + WARNING_OFFSET
            ]:
                self._write_notice(
                    entry,
                    "waitlist_offer_expiring",
                    f"waitlist-expiring:{entry['id']}:{_epoch(entry['offered_at'])}",
                    {
                        "event_request_id": event_id,
                        "expires_at": entry["expires_at"],
                    },
                    now,
                )
                entry["warned_at"] = now
                touched += 1
        return touched

    def pending_outbox(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.outbox if row["published_at"] is None]

    def mark_published(self, ids: list[str], now: Any = None) -> int:
        marked = 0
        for row in self.outbox:
            if row["id"] in ids and row["published_at"] is None:
                row["published_at"] = now or NOW
                marked += 1
        return marked

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
            "warned_at": None,
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
