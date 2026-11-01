"""Tell the requesting Coordinator about a booking decision (SCRUM-15 AC4) or
about a new block that affects their booking (SCRUM-23 AC3).

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

import hashlib
import logging
import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.block_models import VenueBlock
from app.booking_models import BookingRequest

logger = logging.getLogger(__name__)


class BookingNotifier:
    def __init__(self, url: str | None) -> None:
        self._url = url

    def send(self, event: dict[str, Any]) -> bool:
        """Send one event; True only if notificationService accepted it."""
        if self._url is None:
            return False
        try:
            response = httpx.post(
                self._url,
                json=event,
                headers={
                    "X-Internal-Token": os.environ.get("NOTIFICATION_INTERNAL_TOKEN", "")
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            # Log ids only: the receiver URL or response could hold secrets.
            logger.warning(
                "Failed to notify %s of %s for booking request %s",
                event.get("recipient_id"),
                event.get("event_type"),
                event.get("payload", {}).get("booking_request_id"),
            )
            return False
        return True

    def notify_decision(self, booking: BookingRequest, venue_name: str | None) -> None:
        """Send one event for an approved or rejected request."""
        self.send(
            {
                "event_type": f"venue_booking_{booking.status.value}",
                "recipient_id": booking.requested_by,
                "event_id": f"booking-decision:{booking.id}",
                "payload": _decision_payload(booking, venue_name),
            }
        )

    def notify_organiser_of_rejection(
        self, booking: BookingRequest, venue_name: str | None, organiser_id: str
    ) -> None:
        """Tell the event's Organiser a venue was refused (SCRUM-36 AC2).

        Same payload as the Coordinator's notice, under its own key so neither
        notice hides the other. Approvals are not sent: the Organiser can do
        nothing with them.
        """
        self.send(
            {
                "event_type": "venue_booking_rejected",
                "recipient_id": organiser_id,
                "event_id": f"booking-organiser:{booking.id}",
                "payload": _decision_payload(booking, venue_name),
            }
        )


def _decision_payload(booking: BookingRequest, venue_name: str | None) -> dict[str, Any]:
    return {
        "booking_request_id": booking.id,
        "event_request_id": booking.event_request_id,
        "event_name": booking.event_name,
        "venue_id": booking.venue_id,
        "venue_name": venue_name,
        "start_date": booking.start_date.isoformat(),
        "end_date": booking.end_date.isoformat(),
        "slots": [slot.value for slot in booking.slots],
        "start_minute": booking.start_minute,
        "end_minute": booking.end_minute,
        "decision_reason": booking.decision_reason,
        "suggested_alternative": booking.suggested_alternative,
        "decided_by": booking.decided_by,
    }


def block_affects_booking_event(
    block: VenueBlock, booking: BookingRequest, venue_name: str | None
) -> dict[str, Any]:
    """The SCRUM-23 AC3 event for one booking a new block overlaps."""
    pair = hashlib.sha256(f"{block.id}:{booking.id}".encode()).hexdigest()[:48]
    block_data = block.model_dump(mode="json")
    return {
        "event_type": "venue_block_affects_booking",
        "recipient_id": booking.requested_by,
        # Within notificationService's 64-character limit; one per block and booking.
        "event_id": f"block-impact:{pair}",
        "payload": {
            "block_id": block.id,
            "booking_request_id": booking.id,
            "event_request_id": booking.event_request_id,
            "event_name": booking.event_name,
            "venue_id": booking.venue_id,
            "venue_name": venue_name,
            "block_start_date": block_data["start_date"],
            "block_end_date": block_data["end_date"],
            "block_slots": block_data["slots"],
            "block_start_minute": block.start_minute,
            "block_end_minute": block.end_minute,
            "reason_category": block_data["reason_category"],
            "reason_detail": block.reason_detail,
            "booking_start_date": booking.start_date.isoformat(),
            "booking_end_date": booking.end_date.isoformat(),
            "booking_slots": [slot.value for slot in booking.slots],
            "booking_start_minute": booking.start_minute,
            "booking_end_minute": booking.end_minute,
        },
    }


def current_venue_date() -> date:
    """Today in Singapore, where the venues are; a dependency so tests can fix it."""

    return datetime.now(ZoneInfo("Asia/Singapore")).date()


def get_booking_notifier() -> BookingNotifier:
    """FastAPI dependency; the receiver URL is read from the environment."""

    return BookingNotifier(os.getenv("NOTIFICATION_SERVICE_URL") or None)
