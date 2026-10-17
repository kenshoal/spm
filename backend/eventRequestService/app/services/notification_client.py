import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class NotificationClient:
    """Send domain events without failing the originating workflow.

    Assignment and clarification methods remain best-effort side effects.
    Durable outbox methods return acceptance to their relays; review delivery
    records progress only for notificationService's 202 response.
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

    def notify_clarification_requested(
        self, *, event_request_id: str, organiser_id: str, reason: str
    ) -> None:
        """Tell the Organiser what the Coordinator needs clarified (SCRUM-37 AC3).

        Sent once, after the decision is recorded, with no retry: if
        notificationService is down the Organiser still finds the clarification
        on the request itself.
        """
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "clarification_requested",
                    "recipient_id": organiser_id,
                    "payload": {
                        "event_request_id": event_request_id,
                        "reason": reason,
                    },
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify organiser %s of the clarification requested on "
                "event request %s",
                organiser_id,
                event_request_id,
                exc_info=True,
            )

    def notify_event_request_submitted(
        self, *, event_id: str, organiser_id: str, payload: dict[str, Any]
    ) -> bool:
        """Send the Organiser's submission confirmation (SCRUM-37 AC1).

        Returns whether it was delivered, so the outbox relay marks an event as
        published only once notificationService has accepted it.
        """
        if self._url is None:
            return False
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "event_request_submitted",
                    "recipient_id": organiser_id,
                    "event_id": event_id,
                    "payload": payload,
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to send submission confirmation %s to organiser %s",
                event_id,
                organiser_id,
                exc_info=True,
            )
            return False
        return True

    def notify_arrangement_needs_review(
        self, *, event_id: str, recipient_id: str, payload: dict[str, Any]
    ) -> bool:
        """Only durable 202 acceptance permits recording review-delivery progress."""
        if self._url is None:
            return False
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "arrangement_needs_review",
                    "recipient_id": recipient_id,
                    "event_id": event_id,
                    "payload": payload,
                },
                timeout=5,
            )
            if response.status_code != 202:
                logger.warning(
                    "Review notification %s was not accepted for %s",
                    event_id,
                    recipient_id,
                )
                return False
        except httpx.HTTPError:
            logger.warning(
                "Review notification %s could not reach recipient %s",
                event_id,
                recipient_id,
                exc_info=True,
            )
            return False
        return True
