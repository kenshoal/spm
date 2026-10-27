"""Pure rules for the event waiting list (SCRUM-24).

These mirror what the database functions enforce (D10), so the API can refuse
early and the timer can decide its passes. The database stays authoritative:
it re-checks under the event row lock.

Decisions referenced here live in docs/testcases/scrum_24_testcases.md:
D1 inclusive 72h acceptance window, D2 warning at T0 + 48h, D3 expired
attendees requeue at the back, D6 pending offers hold capacity, D7 per-place
offer history, D8 offer cut-off and D11 closing at the cut-off.
"""

from datetime import datetime, timedelta
from typing import Any

OFFER_WINDOW = timedelta(hours=72)  # D1: accept at or before offered_at + 72h
WARNING_OFFSET = timedelta(hours=48)  # D2: warning 24h before expiry

WAITING = "Waiting"
OFFERED = "Offered"
ACCEPTED = "Accepted"
WITHDRAWN = "Withdrawn"
CLOSED = "Closed"
LAPSED = "Lapsed"
REVOKED = "Revoked"


class WaitlistRuleError(Exception):
    """A refusal the service maps to 409 with this `code` (D10)."""

    code = "waitlist_refused"


class PlacesAvailableError(WaitlistRuleError):
    """The event still has free places, so joining the list is refused."""

    code = "places_available"


class AlreadyRegisteredError(WaitlistRuleError):
    code = "already_registered"


class AlreadyWaitlistedError(WaitlistRuleError):
    code = "already_waitlisted"


class NotOfferedError(WaitlistRuleError):
    code = "not_offered"


class OfferExpiredError(WaitlistRuleError):
    code = "offer_expired"


def _as_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def check_join(
    event: dict[str, Any],
    now: datetime,
    places_taken: int,
    is_registered: bool,
    active_entry: dict[str, Any] | None,
) -> None:
    """Raise unless the attendee may join `event`'s waiting list at `now`.

    `places_taken` counts Registered registrations plus Offered entries (D6):
    a pending offer holds its place, so a full event is joinable (AC1-B1) and
    an event with a free place is not (AC1-N1).
    """
    raise NotImplementedError


def check_accept(entry: dict[str, Any] | None, now: datetime) -> None:
    """D1: accepting at or before `expires_at` succeeds; after it, refuse."""
    raise NotImplementedError


def offer_deadline(offered_at: datetime | str) -> datetime:
    """D1: the acceptance window ends exactly 72h after the offer."""
    raise NotImplementedError


def expiry_due(entry: dict[str, Any], now: datetime) -> bool:
    """Strictly after `expires_at` (D1): accepting exactly at it still wins."""
    raise NotImplementedError


def warning_due(entry: dict[str, Any], now: datetime) -> bool:
    """D2: one `waitlist_offer_expiring` at offered_at + 48h, never repeated."""
    raise NotImplementedError


def may_issue_offer(now: datetime, event_start: datetime | str) -> bool:
    """D8 (#116): issue a new offer only if its window ends before start.

    Strict: an offer made exactly 72h before start would end at the start
    instant and is not issued; the place opens to registration instead (D12)
    and the list closes (D11).
    """
    raise NotImplementedError


def requeue(entry: dict[str, Any], now: datetime) -> dict[str, Any]:
    """D3: an expired offeree goes to the back with a fresh `queued_at`."""
    raise NotImplementedError


def waiting_order(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Waiting entries in queue order: `queued_at`, then `seq`."""
    raise NotImplementedError


def next_recipient(
    entries: list[dict[str, Any]],
    place_id: str,
    place_offers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """D7 FIFO: the earliest Waiting attendee never lapsed on this place.

    Only outcome `Lapsed` in the per-place history bars a re-offer; a revoked
    holder is eligible for the same place again (AC3-H2). Returns None when
    nobody is eligible, so the caller releases the place to registration
    (D7/D12).
    """
    raise NotImplementedError
