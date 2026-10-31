"""Deliver the waiting-list notices the database stored (SCRUM-24 AC5).

The database functions write each notice into `waitlist_notification_outbox`
inside the transaction that made the change, so a rollback sends nothing and
an outage never undoes a change. This relay delivers those notices after the
fact: a notice is marked published only once notificationService has accepted
it (202), so an outage keeps it pending and the next pass retries it, and the
unique idempotency key means the retry is stored once (AC5-N1).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol


class WaitlistOutboxRepository(Protocol):
    def pending_outbox(self) -> list[dict[str, Any]]: ...

    def mark_published(self, ids: list[str], now: Any = None) -> int: ...


class WaitlistNotificationRelay:
    def __init__(
        self,
        repository: WaitlistOutboxRepository,
        notification_client: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._notifications = notification_client
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_once(self) -> int:
        """Deliver every pending notice once; returns how many were accepted."""
        delivered = 0
        now = self._clock()
        for row in self._repository.pending_outbox():
            sent = self._notifications.notify_waitlist_notice(
                event_type=row["event_type"],
                recipient_id=row["recipient_id"],
                idempotency_key=row["idempotency_key"],
                payload=row["payload"],
            )
            if sent:
                delivered += self._repository.mark_published([row["id"]], now)
        return delivered
