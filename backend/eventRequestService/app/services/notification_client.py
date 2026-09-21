import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class NotificationClient:
    """Hook for a future Notification System — no such service exists yet,
    so without notification_service_url configured this is a no-op. A
    failed or unreachable notification is logged, never raised: notifying
    is a side effect of assignment, not part of its contract, and must
    never be the reason an assignment fails.
    """

    def __init__(self, notification_service_url: str | None) -> None:
        self._url = notification_service_url

    @classmethod
    def from_settings(cls, settings: Settings) -> "NotificationClient":
        url = (
            str(settings.notification_service_url)
            if settings.notification_service_url
            else None
        )
        return cls(url)

    def notify_coordinator_assigned(
        self, *, event_request_id: str, coordinator_id: str, assigned_by: str
    ) -> None:
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "coordinator_assigned",
                    "recipient_id": coordinator_id,
                    "payload": {
                        "event_request_id": event_request_id,
                        "coordinator_id": coordinator_id,
                        "assigned_by": assigned_by,
                    },
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify coordinator %s of assignment to event request %s",
                coordinator_id,
                event_request_id,
                exc_info=True,
            )
