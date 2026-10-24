"""Pure rules for attendee registration (SCRUM-21).

These mirror what `register_for_event` enforces in the database, so the API can
refuse early and the public view can say how many places remain. The database
function stays authoritative: it re-checks under a row lock.
"""

from datetime import datetime
from typing import Any

CONFIRMED = "Confirmed"

PUBLIC_EVENT_FIELDS = (
    "id",
    "event_name",
    "purpose",
    "description",
    "proposed_date_times",
    "registration_opens_at",
    "registration_closes_at",
    "registration_capacity",
    "places_remaining",
)


class EventNotVisibleError(Exception):
    """The event is missing or not Confirmed, so attendees may not see it."""


class RegistrationNotOpenError(Exception):
    """The window is unset, not yet open or closed, or capacity is unset."""


class EventFullError(Exception):
    """Every place is taken."""


class WithdrawalNotPermittedError(Exception):
    """The event is not Confirmed, has started, or has no start date (SCRUM-22 D1)."""


class AlreadyWithdrawnError(Exception):
    """The registration was already withdrawn."""


class RegistrationNotFoundError(Exception):
    """The registration is unknown or belongs to someone else."""


def _as_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def is_window_open(event: dict[str, Any], now: datetime) -> bool:
    """Open from opens_at (inclusive) until closes_at (exclusive); unset = closed."""
    opens = _as_datetime(event.get("registration_opens_at"))
    closes = _as_datetime(event.get("registration_closes_at"))
    if opens is None or closes is None or event.get("registration_capacity") is None:
        return False
    return opens <= now < closes


def check_registration(
    event: dict[str, Any], now: datetime, registered_count: int
) -> None:
    """Raise unless an attendee may register for `event` at `now`."""
    if event.get("status") != CONFIRMED:
        raise EventNotVisibleError
    if not is_window_open(event, now):
        raise RegistrationNotOpenError
    if registered_count >= event["registration_capacity"]:
        raise EventFullError


def places_remaining(event: dict[str, Any], registered_count: int) -> int | None:
    capacity = event.get("registration_capacity")
    if capacity is None:
        return None
    return max(capacity - registered_count, 0)


def to_public_event(event: dict[str, Any], registered_count: int) -> dict[str, Any]:
    """Whitelist projection: nothing outside PUBLIC_EVENT_FIELDS is ever returned."""
    public = {
        field: event.get(field)
        for field in PUBLIC_EVENT_FIELDS
        if field != "places_remaining"
    }
    public["places_remaining"] = places_remaining(event, registered_count)
    return public


def event_start(event: dict[str, Any]) -> datetime | None:
    """The earliest proposed date, or None when the event has no dates."""
    starts = [
        parsed
        for value in event.get("proposed_date_times") or []
        if (parsed := _as_datetime(value)) is not None
    ]
    return min(starts) if starts else None


def check_withdrawal(
    event: dict[str, Any], registration: dict[str, Any], now: datetime
) -> None:
    """Raise unless the attendee may withdraw `registration` at `now` (SCRUM-22 D1).

    Same order as `withdraw_registration`: already withdrawn first, then the
    event must be Confirmed and not yet started (`now` strictly before the
    earliest date). The registration window plays no part: a place can be
    released after sign-ups close.
    """
    if registration.get("status") == "Withdrawn":
        raise AlreadyWithdrawnError
    start = event_start(event)
    if event.get("status") != CONFIRMED or start is None or now >= start:
        raise WithdrawalNotPermittedError
