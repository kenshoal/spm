"""Expire tentative venue holds and tell their coordinator (SCRUM-18).

``run_hold_sweep`` asks the hold store which holds have expired and which
notices are due, sends each notice to notificationService, and records it only
once it was accepted. The event_id is fixed per hold and kind, and
notificationService stores one notification per recipient and event_id, so a
retry after a failed record never shows a notice twice. A notice that failed to
send stays due and is retried on the next run, which also catches up after
downtime.

``run_forever`` repeats the sweep on an interval for the running service.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.booking_notifications import BookingNotifier
from app.hold_models import HoldNotice
from app.hold_store import VenueHoldStore

logger = logging.getLogger(__name__)


def hold_notice_event(notice: HoldNotice) -> dict[str, Any]:
    """The notificationService event for one hold notice."""
    return {
        "event_type": f"venue_hold_{notice.kind}",
        "recipient_id": notice.recipient_id,
        # Within notificationService's 64-character limit; one per hold and kind.
        "event_id": f"hold-{notice.kind}:{notice.hold_id}",
        "payload": notice.model_dump(mode="json"),
    }


def run_hold_sweep(
    store: VenueHoldStore, notifier: BookingNotifier, now: datetime | None = None,
) -> int:
    """Expire holds and send the due notices; returns how many were delivered."""
    delivered = 0
    for notice in store.sweep(now or datetime.now(UTC)):
        if notifier.send(hold_notice_event(notice)):
            store.mark_notice(notice.hold_id, notice.kind)
            delivered += 1
    return delivered


async def run_forever(
    store: VenueHoldStore, notifier: BookingNotifier, interval_seconds: float,
) -> None:
    """Sweep every ``interval_seconds`` until cancelled; a failed run is logged."""
    while True:
        try:
            await asyncio.to_thread(run_hold_sweep, store, notifier)
        except Exception:  # keep sweeping after any failure
            logger.exception("Venue hold sweep failed")
        await asyncio.sleep(interval_seconds)
