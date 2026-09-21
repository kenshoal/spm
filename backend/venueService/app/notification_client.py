"""Outgoing hook for the future notification system, matching eventRequestService."""

import logging
from typing import Annotated

import httpx
from fastapi import Depends

from app.block_models import VenueBlock
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class NotificationClient:
    """No URL means no delivery attempt. HTTP failures never undo a saved block.

    The caller must first identify a confirmed upcoming event affected by this
    saved block and resolve its assigned Coordinator from trusted service data.
    This client does not discover recipients, send emails, or persist retries.
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

    def notify_venue_block_applied(
        self,
        *,
        block: VenueBlock,
        event_request_id: str,
        coordinator_id: str,
    ) -> None:
        """Request an alert for one affected event; IDs are supplied server-side.

        Dates/slots in the payload describe the block's inclusive period, not
        the event's schedule. The event type/payload are a proposed contract for
        the eventual notification receiver. A successful HTTP response only
        confirms acceptance by that receiver, not delivery to a person.
        """
        if self._url is None:
            return
        block_data = block.model_dump(mode="json")
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "venue_block_applied",
                    "recipient_id": coordinator_id,
                    "payload": {
                        "event_request_id": event_request_id,
                        "coordinator_id": coordinator_id,
                        "block_id": block.id,
                        "venue_id": block.venue_id,
                        "start_date": block_data["start_date"],
                        "end_date": block_data["end_date"],
                        "slots": block_data["slots"],
                        "reason_category": block_data["reason_category"],
                        "reason_detail": block.reason_detail,
                        "created_by": block.created_by,
                    },
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            # Don't log the URL, response body or exception text: a receiver URL
            # may contain credentials. Retain IDs for tracing delivery failures.
            logger.warning(
                "Failed to notify coordinator %s of venue block %s affecting event %s",
                coordinator_id,
                block.id,
                event_request_id,
            )


def get_notification_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationClient:
    """Dependency for the eventual affected-event workflow; no requests on creation."""
    return NotificationClient.from_settings(settings)
