"""The waiting-list timer: one pass of expiries, warnings and closings (SCRUM-24).

Registered as one more PeriodicTaskRunner handler behind its own switch, like
SCRUM-40's auto-completion. One run calls `process_waitlist_timers(now)` —
which locks each event in turn and is idempotent (AC4-X1) — and then delivers
the notices that pass wrote, so a delivered notice never precedes its saved
change.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from app.services.waitlist_notification_relay import WaitlistNotificationRelay


class WaitlistTimerRepository(Protocol):
    def process_waitlist_timers(self, now: datetime) -> int: ...


class WaitlistTimer:
    def __init__(
        self,
        repository: WaitlistTimerRepository,
        relay: WaitlistNotificationRelay | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._relay = relay
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_once(self, as_of: datetime | None = None) -> dict[str, int]:
        now = self._clock() if as_of is None else as_of
        processed = self._repository.process_waitlist_timers(now)
        delivered = self._relay.run_once() if self._relay is not None else 0
        return {"entries_processed": processed, "notices_delivered": delivered}


def build_waitlist_timer() -> WaitlistTimer:
    """The served timer: the Supabase repository, the relay, the real clock."""
    from app.config import get_notification_settings, get_settings
    from app.repositories.waitlist_repository import SupabaseWaitlistRepository
    from app.services.notification_client import NotificationClient

    repository = SupabaseWaitlistRepository.from_settings(get_settings())
    client = NotificationClient.from_settings(get_notification_settings())
    return WaitlistTimer(repository, WaitlistNotificationRelay(repository, client))
