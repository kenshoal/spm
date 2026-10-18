"""At-least-once review delivery with durable per-recipient progress."""

import asyncio
import logging
import threading
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.repositories.arrangement_review_notification_repository import (
    ArrangementReviewNotificationRepository,
    SupabaseArrangementReviewNotificationRepository,
)
from app.services.notification_client import NotificationClient

logger = logging.getLogger(__name__)


class ArrangementReviewNotifier(Protocol):
    def notify_arrangement_needs_review(
        self, *, event_id: str, recipient_id: str, payload: dict[str, Any]
    ) -> bool: ...


class ArrangementReviewNotificationRelay:
    def __init__(
        self,
        repository: ArrangementReviewNotificationRepository,
        notifier: ArrangementReviewNotifier,
        *,
        batch_size: int = 50,
        interval_seconds: float = 10,
    ) -> None:
        self._repository = repository
        self._notifier = notifier
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stopping = threading.Event()

    @classmethod
    def from_settings(
        cls, settings: Settings
    ) -> "ArrangementReviewNotificationRelay | None":
        if settings.notification_service_url is None:
            return None
        return cls(
            SupabaseArrangementReviewNotificationRepository.from_settings(settings),
            NotificationClient.from_settings(settings),
        )

    def relay_once(self) -> int:
        completed = 0
        for job in self._repository.list_pending(limit=self._batch_size):
            if self._stopping.is_set():
                break
            review_id = job["review_id"]
            try:
                snapshot = self._repository.begin_attempt(review_id)
                if snapshot is None:
                    continue
                if not snapshot["recipients_available"]:
                    logger.warning(
                        "Recipient lookup unavailable for review %s", review_id
                    )
                    continue
                payload = dict(snapshot["payload"])
                # Only the native same-event Approved-record lookup adds this key.
                if snapshot.get("change_request_id") is not None:
                    payload["change_request_id"] = snapshot["change_request_id"]
                event_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"needs-review:{payload['trigger_id']}:{payload['arrangement_id']}",
                    )
                )
                recipients = set(snapshot["domain_recipient_ids"])
                if snapshot["coordinator_id"]:
                    recipients.add(snapshot["coordinator_id"])
                accepted = snapshot["accepted_recipients"]
                for recipient_id in sorted(recipients):
                    if self._stopping.is_set():
                        break
                    if recipient_id in accepted:
                        continue
                    try:
                        if self._notifier.notify_arrangement_needs_review(
                            event_id=event_id,
                            recipient_id=recipient_id,
                            payload=payload,
                        ):
                            self._repository.record_accepted(review_id, recipient_id)
                    except Exception:
                        logger.exception(
                            "Recipient attempt failed for %s/%s",
                            review_id,
                            recipient_id,
                        )
                # Native completion checks both CURRENT groups and their acceptance.
                if self._repository.complete_if_resolved(review_id):
                    completed += 1
            except Exception:
                logger.exception("Review notification attempt failed for %s", review_id)
        return completed

    async def run_forever(self) -> None:
        try:
            while not self._stopping.is_set():
                attempt = asyncio.create_task(asyncio.to_thread(self.relay_once))
                try:
                    await asyncio.shield(attempt)
                except asyncio.CancelledError:
                    self._stopping.set()
                    # Finish the bounded in-flight operation before closing its
                    # client. The stop flag prevents later recipient/job sends.
                    await attempt
                    raise
                except Exception:
                    logger.exception("Review relay pass failed; retrying")
                await asyncio.sleep(self._interval_seconds)
        finally:
            self._stopping.set()
            close = getattr(self._repository, "close", None)
            if callable(close):
                close()


def build_arrangement_review_notification_relay() -> (
    ArrangementReviewNotificationRelay | None
):
    try:
        return ArrangementReviewNotificationRelay.from_settings(get_settings())
    except ValidationError:
        return None
