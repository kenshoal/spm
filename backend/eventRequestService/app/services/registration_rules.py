"""Pure rules for attendee registration (SCRUM-21).

Stubs: the rules are implemented in the Green commit that follows the Red tests.
"""

from datetime import datetime
from typing import Any

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


def check_registration(
    event: dict[str, Any], now: datetime, registered_count: int
) -> None:
    raise NotImplementedError


def places_remaining(event: dict[str, Any], registered_count: int) -> int | None:
    raise NotImplementedError


def to_public_event(event: dict[str, Any], registered_count: int) -> dict[str, Any]:
    raise NotImplementedError
