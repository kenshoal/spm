"""Waiting-list persistence through Supabase's Data API (SCRUM-24).

SupabaseWaitlistRepository extends the registration repository with the
`join_waitlist` RPC and the reads the service needs, sharing its client and
error mapping; the database function re-checks every rule under the event row
lock.
"""

from datetime import datetime
from typing import Any, Protocol

import httpx

from app.repositories import SupabaseRepositoryError
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
    def process_waitlist_timers(self, now: datetime) -> int:
        """Run one timer pass. The function returns nothing, so the count is 0."""
        try:
            response = self._client.post(
                "/rpc/process_waitlist_timers", json={"p_now": now.isoformat()}
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the waiting-list timer pass"
            ) from error
        return 0

    def pending_outbox(self) -> list[dict[str, Any]]:
        return self._get(
            "/waitlist_notification_outbox",
            {
                "select": "id,recipient_id,event_type,idempotency_key,payload",
                "published_at": "is.null",
                "order": "occurred_at.asc",
            },
        )

    def mark_published(self, ids: list[str], now: Any = None) -> int:
        """Stamp the delivered notices; a row already stamped is left alone."""
        if not ids:
            return 0
        try:
            response = self._client.patch(
                "/waitlist_notification_outbox",
                params={"id": f"in.({','.join(ids)})", "published_at": "is.null"},
                json={"published_at": now.isoformat()},
                headers={"Prefer": "return=representation"},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not mark the waiting-list notices published"
            ) from error
        return len(response.json())

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
        """The caller's current entries, oldest first, with their positions.

        A position is the attendee's place in their event's Waiting queue
        (AC1-H3); the offered holder is out of the queue and shows none, and
        so does an entry the cut-off closed (AC10-H1), which stays listed so
        the attendee can see the list closed.
        The database could rank with a window function, but the Data API
        cannot, so the Waiting entries of the caller's events are read.
        """
        mine = self._get(
            "/event_waitlist_entries",
            {
                "select": WAITLIST_ENTRY_COLUMNS,
                "attendee_id": f"eq.{attendee_id}",
                "status": "in.(Waiting,Offered,Closed)",
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
