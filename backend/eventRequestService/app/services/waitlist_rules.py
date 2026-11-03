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

from app.services.registration_rules import (
    CONFIRMED,
    EventNotVisibleError,
    RegistrationNotOpenError,
    is_window_open,
)

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
    """A refusal the service maps to a JSON error with this `code` (D10)."""

    code = "waitlist_refused"
    detail = "This waiting-list action was refused"
    status = 409

class CoordinatorNotAssignedError(WaitlistRuleError):
    """Only the event's assigned Coordinator may choose a recipient (D9)."""

    status = 403
    code = "not_assigned"
    detail = "Only the event's assigned Coordinator can choose a recipient"


class WaitlistEntryNotFoundError(WaitlistRuleError):
    """Someone else's entry, an unknown id or a Closed entry (404, D10)."""

    status = 404
    code = "entry_not_found"
    detail = "Entry not found"


class PlacesAvailableError(WaitlistRuleError):
    """The event still has free places, so joining the list is refused."""

    code = "places_available"
    detail = "This event still has places available"


class AlreadyRegisteredError(WaitlistRuleError):
    code = "already_registered"
    detail = "You are already registered for this event"


class AlreadyWaitlistedError(WaitlistRuleError):
    code = "already_waitlisted"
    detail = "You are already on the waiting list for this event"


class NotOfferedError(WaitlistRuleError):
    code = "not_offered"
    detail = "This entry holds no offer"


class OfferExpiredError(WaitlistRuleError):
    code = "offer_expired"
    detail = "This offer has expired"


class AlreadyWithdrawnError(WaitlistRuleError):
    code = "already_withdrawn"
    detail = "This entry is already withdrawn"


class NotWaitingError(WaitlistRuleError):
    code = "not_waiting"
    detail = "That entry is not waiting"


class NoOpenPlaceError(WaitlistRuleError):
    code = "no_open_place"
    detail = "This event has no open place to assign"


class OfferWindowClosedError(WaitlistRuleError):
    code = "offer_window_closed"
    detail = (
        "An offer needs 72 hours before registration closes and before the event "
        "starts, and there is not enough time left"
    )


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
    an event with a free place is not (AC1-N1). A non-Confirmed event is not
    visible at all (D8), like SCRUM-21.
    """
    if event.get("status") != CONFIRMED:
        raise EventNotVisibleError
    if not is_window_open(event, now):
        raise RegistrationNotOpenError
    if is_registered:
        raise AlreadyRegisteredError
    if active_entry is not None:
        raise AlreadyWaitlistedError
    if places_taken < event["registration_capacity"]:
        raise PlacesAvailableError


def check_accept(entry: dict[str, Any] | None, now: datetime) -> None:
    """D1: accepting at or before `expires_at` succeeds; after it, refuse."""
    if entry is None or entry.get("status") != OFFERED:
        raise NotOfferedError
    expires = _as_datetime(entry.get("expires_at"))
    if expires is None or now > expires:
        raise OfferExpiredError


def offer_deadline(offered_at: datetime | str) -> datetime:
    """D1: the acceptance window ends exactly 72h after the offer."""
    offered = _as_datetime(offered_at)
    assert offered is not None
    return offered + OFFER_WINDOW


def expiry_due(entry: dict[str, Any], now: datetime) -> bool:
    """Strictly after `expires_at` (D1): accepting exactly at it still wins."""
    if entry.get("status") != OFFERED:
        return False
    expires = _as_datetime(entry.get("expires_at"))
    return expires is not None and now > expires


def warning_due(entry: dict[str, Any], now: datetime) -> bool:
    """D2: one `waitlist_offer_expiring` at offered_at + 48h, never repeated."""
    if entry.get("status") != OFFERED or entry.get("warned_at") is not None:
        return False
    offered = _as_datetime(entry.get("offered_at"))
    return offered is not None and now >= offered + WARNING_OFFSET


def may_issue_offer(now: datetime, event_start: datetime | str) -> bool:
    """D8 (#116): issue a new offer only if its window ends before start.

    Strict: an offer made exactly 72h before start would end at the start
    instant and is not issued; the place opens to registration instead (D12)
    and the list closes (D11).
    """
    start = _as_datetime(event_start)
    return start is not None and now + OFFER_WINDOW < start


def requeue(entry: dict[str, Any], now: datetime) -> dict[str, Any]:
    """D3: an expired offeree goes to the back with a fresh `queued_at`."""
    requeued = dict(entry)
    requeued.update(
        {
            "status": WAITING,
            "queued_at": now,
            "offered_at": None,
            "expires_at": None,
            "warned_at": None,
            "place_id": None,
        }
    )
    return requeued


def waiting_order(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Waiting entries in queue order: `queued_at`, then `seq`."""
    waiting = [entry for entry in entries if entry.get("status") == WAITING]
    return sorted(
        waiting,
        key=lambda entry: (
            _as_datetime(entry.get("queued_at")),
            entry.get("seq") or 0,
        ),
    )


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
    lapsed = {
        offer["attendee_id"]
        for offer in place_offers
        if offer.get("place_id") == place_id and offer.get("outcome") == LAPSED
    }
    for entry in waiting_order(entries):
        if entry["attendee_id"] not in lapsed:
            return entry
    return None
