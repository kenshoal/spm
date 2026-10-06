import asyncio
import logging
from typing import Any, Protocol

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.repositories import OutboxRepository, SupabaseOutboxRepository
from app.services.notification_client import NotificationClient

logger = logging.getLogger(__name__)


class SubmissionNotifier(Protocol):
    def notify_event_request_submitted(
        self, *, event_id: str, organiser_id: str, payload: dict[str, Any]
    ) -> bool: ...


class OutboxRelay:
    """Delivers submission events from event_request_outbox to notificationService,
    so each Organiser gets a confirmation (SCRUM-37 AC1).

    Delivery is at least once: an event is marked published only after
    notificationService accepts it, so a failure in between re-sends it on the
    next pass. notificationService stores a repeated event_id once, so the
    Organiser still sees one confirmation. The outbox holds only
    `event_request.submitted` events (CHECK constraint in migration 0008).
    """

    def __init__(
        self,
        repository: OutboxRepository,
        notifier: SubmissionNotifier,
        *,
        batch_size: int = 50,
        interval_seconds: float = 10,
    ) -> None:
        self._repository = repository
        self._notifier = notifier
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> "OutboxRelay | None":
        # Nobody to deliver to: leave events unpublished rather than consume them.
        if settings.notification_service_url is None:
            return None
        return cls(
            SupabaseOutboxRepository.from_settings(settings),
            NotificationClient.from_settings(settings),
        )

    def relay_once(self) -> int:
        """Deliver one batch of unpublished events; return how many were delivered."""
        delivered = 0
        for event in self._repository.list_unpublished(limit=self._batch_size):
            if self._notifier.notify_event_request_submitted(
                event_id=event["id"],
                organiser_id=event["organiser_id"],
                payload=event["payload"],
            ):
                self._repository.mark_published(event["id"])
                delivered += 1
        return delivered

    async def run_forever(self) -> None:
        while True:
            try:
                # The repository and client are synchronous; keep them off the
                # event loop so requests are not blocked while a pass runs.
                await asyncio.to_thread(self.relay_once)
            except Exception:
                # A background task that raises dies silently, so log and carry on.
                logger.exception(
                    "Outbox relay pass failed; retrying in %ss", self._interval_seconds
                )
            await asyncio.sleep(self._interval_seconds)


def build_outbox_relay() -> OutboxRelay | None:
    """The relay for this process, or None when Supabase or notificationService
    is not configured."""
    try:
        settings = get_settings()
    except ValidationError:
        return None
    return OutboxRelay.from_settings(settings)
