"""Tell the requesting Coordinator about a booking decision (SCRUM-15 AC4).

Follows eventRequestService's NotificationClient: events go to
notificationService's ``POST /notifications/events`` (SCRUM-37). Without
``NOTIFICATION_SERVICE_URL`` nothing is sent. A failed or unreachable receiver
is logged, never raised: notifying is a side effect of a saved decision and
must never undo or fail it. Refused approvals send nothing.

The recipient is ``requested_by``, the Coordinator who raised the request, as
the acceptance criterion says. ``event_id`` makes a retried decision event
idempotent in notificationService.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.booking_models import BookingRequest

logger = logging.getLogger(__name__)


class BookingNotifier:
    def __init__(self, url: str | None) -> None:
        self._url = url

    def send(self, event: dict[str, Any]) -> None:
        if self._url is None:
            return
        try:
            response = httpx.post(self._url, json=event, timeout=5)
            response.raise_for_status()
        except httpx.HTTPError:
            # Log ids only: the receiver URL or response could hold secrets.
            logger.warning(
                "Failed to notify %s of %s for booking request %s",
                event.get("recipient_id"),
                event.get("event_type"),
                event.get("payload", {}).get("booking_request_id"),
            )

    def notify_decision(self, booking: BookingRequest, venue_name: str | None) -> None:
        """Send one event for an approved or rejected request."""
        self.send(
            {
                "event_type": f"venue_booking_{booking.status.value}",
                "recipient_id": booking.requested_by,
                "event_id": f"booking-decision:{booking.id}",
                "payload": {
                    "booking_request_id": booking.id,
                    "event_request_id": booking.event_request_id,
                    "event_name": booking.event_name,
                    "venue_id": booking.venue_id,
                    "venue_name": venue_name,
                    "start_date": booking.start_date.isoformat(),
                    "end_date": booking.end_date.isoformat(),
                    "slots": [slot.value for slot in booking.slots],
                    "decision_reason": booking.decision_reason,
                    "suggested_alternative": booking.suggested_alternative,
                    "decided_by": booking.decided_by,
                },
            }
        )


def get_booking_notifier() -> BookingNotifier:
    """FastAPI dependency; the receiver URL is read from the environment."""

    return BookingNotifier(os.getenv("NOTIFICATION_SERVICE_URL") or None)
