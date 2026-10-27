"""Waiting-list persistence through Supabase's Data API (SCRUM-24).

SupabaseWaitlistRepository extends the registration repository with the
`join_waitlist` RPC and the reads the service needs, sharing its client and
error mapping; the database function re-checks every rule under the event row
lock.
"""

from datetime import datetime
from typing import Any, Protocol

from app.repositories.registration_repository import SupabaseRegistrationRepository

WAITLIST_ENTRY_COLUMNS = (
    "id,event_request_id,attendee_id,status,queued_at,seq,offered_at,expires_at"
)


class WaitlistRepository(Protocol):
    def get_event(self, event_id: str) -> dict[str, Any] | None: ...

    def has_active(self, event_id: str, attendee_id: str) -> bool: ...

    def places_taken(self, event_id: str) -> int: ...

    def active_entry(
        self, event_id: str, attendee_id: str
    ) -> dict[str, Any] | None: ...

    def join_waitlist(
        self, event_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]: ...

    def accept_waitlist_offer(
        self, entry_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]: ...

    def withdraw_from_waitlist(
        self, entry_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]: ...

    def choose_waitlist_recipient(
        self, event_id: str, entry_id: str, coordinator_id: str, now: datetime
    ) -> dict[str, Any]: ...

    def list_entries_for(self, attendee_id: str) -> list[dict[str, Any]]: ...


class SupabaseWaitlistRepository(SupabaseRegistrationRepository):
    def active_entry(
        self, event_id: str, attendee_id: str
    ) -> dict[str, Any] | None:
        """The attendee's one active (Waiting/Offered) entry for the event."""
        rows = self._get(
            "/event_waitlist_entries",
            {
                "select": WAITLIST_ENTRY_COLUMNS,
                "event_request_id": f"eq.{event_id}",
                "attendee_id": f"eq.{attendee_id}",
                "status": "in.(Waiting,Offered)",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def join_waitlist(
        self, event_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        return self._rpc(
            "join_waitlist",
            {
                "p_event_request_id": event_id,
                "p_attendee_id": attendee_id,
                "p_now": now.isoformat(),
            },
            action="waitlist join",
        )

    def accept_waitlist_offer(
        self, entry_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        return self._rpc(
            "accept_waitlist_offer",
            {
                "p_entry_id": entry_id,
                "p_attendee_id": attendee_id,
                "p_now": now.isoformat(),
            },
            action="acceptance",
        )

    def withdraw_from_waitlist(
        self, entry_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        return self._rpc(
            "withdraw_from_waitlist",
            {
                "p_entry_id": entry_id,
                "p_attendee_id": attendee_id,
                "p_now": now.isoformat(),
            },
            action="withdrawal",
        )

    def choose_waitlist_recipient(
        self, event_id: str, entry_id: str, coordinator_id: str, now: datetime
    ) -> dict[str, Any]:
        return self._rpc(
            "choose_waitlist_recipient",
            {
                "p_event_request_id": event_id,
                "p_entry_id": entry_id,
                "p_coordinator_id": coordinator_id,
                "p_now": now.isoformat(),
            },
            action="recipient choice",
        )

    def list_entries_for(self, attendee_id: str) -> list[dict[str, Any]]:
        """The caller's active entries, oldest first, with their positions.

        A position is the attendee's place in their event's Waiting queue
        (AC1-H3); the offered holder is out of the queue and shows none.
        The database could rank with a window function, but the Data API
        cannot, so the Waiting entries of the caller's events are read.
        """
        mine = self._get(
            "/event_waitlist_entries",
            {
                "select": WAITLIST_ENTRY_COLUMNS,
                "attendee_id": f"eq.{attendee_id}",
                "status": "in.(Waiting,Offered)",
                "order": "queued_at.asc,seq.asc",
            },
        )
        if not mine:
            return []
        event_ids = sorted({row["event_request_id"] for row in mine})
        queue = self._get(
            "/event_waitlist_entries",
            {
                "select": "id,event_request_id",
                "event_request_id": f"in.({','.join(event_ids)})",
                "status": "eq.Waiting",
                "order": "queued_at.asc,seq.asc",
            },
        )
        ranks: dict[str, int] = {}
        per_event: dict[str, int] = {}
        for row in queue:
            per_event[row["event_request_id"]] = (
                per_event.get(row["event_request_id"], 0) + 1
            )
            ranks[row["id"]] = per_event[row["event_request_id"]]
        return [dict(row, position=ranks.get(row["id"])) for row in mine]
