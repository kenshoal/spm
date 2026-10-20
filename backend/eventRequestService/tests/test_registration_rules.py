"""SCRUM-21: pure registration rules (AC1-X1, AC2-P, AC3-B/N/X, AC4-B/N)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services.registration_rules import (
    PUBLIC_EVENT_FIELDS,
    EventFullError,
    EventNotVisibleError,
    RegistrationNotOpenError,
    check_registration,
    places_remaining,
    to_public_event,
)

OPENS = datetime(2030, 1, 10, 9, 0, tzinfo=UTC)
CLOSES = datetime(2030, 1, 20, 9, 0, tzinfo=UTC)
ONE_SECOND = timedelta(seconds=1)
INSIDE = OPENS + timedelta(days=1)

NON_CONFIRMED = [
    "Draft",
    "Submitted",
    "Under Review",
    "Changes Requested",
    "Rejected",
    "Approved",
    "Planning",
    "Safety Review",
    "Completed",
    "Cancelled",
]


def make_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": "7b0f6c1e-0000-4000-8000-000000000001",
        "organiser_id": "organiser-1",
        "status": "Confirmed",
        "event_name": "Community Dinner",
        "purpose": "Bring neighbours together",
        "description": "A shared meal",
        "proposed_date_times": [datetime(2030, 2, 1, 18, 0, tzinfo=UTC)],
        "expected_attendance": 40,
        "venue_requirements": "Hall with kitchen",
        "accessibility_needs": "Step-free access",
        "equipment_requirements": "Tables",
        "registration_needs": "Dietary notes",
        "registration_opens_at": OPENS,
        "registration_closes_at": CLOSES,
        "registration_capacity": 10,
    }
    event.update(overrides)
    return event


# AC1-X1 (cross-cutting): the public projection carries exactly the D4 fields
def test_public_event_has_exactly_the_whitelisted_fields() -> None:
    public = to_public_event(make_event(), registered_count=3)

    assert set(public) == set(PUBLIC_EVENT_FIELDS)
    assert public["places_remaining"] == 7
    assert public["event_name"] == "Community Dinner"
    for internal in ("organiser_id", "status", "venue_requirements",
                     "accessibility_needs", "equipment_requirements",
                     "registration_needs", "expected_attendance"):
        assert internal not in public


@pytest.mark.parametrize("status", NON_CONFIRMED,
                         ids=[f"AC2-P{k}" for k in range(1, 11)])
# AC2-P1..P10 (partition): every non-Confirmed status is not visible, even with an open window
def test_non_confirmed_event_is_not_visible(status: str) -> None:
    with pytest.raises(EventNotVisibleError):
        check_registration(make_event(status=status), INSIDE, registered_count=0)


# AC3-B1 (boundary): one second before the window opens is refused
def test_refused_one_second_before_opening() -> None:
    with pytest.raises(RegistrationNotOpenError):
        check_registration(make_event(), OPENS - ONE_SECOND, registered_count=0)


# AC3-B2 (boundary): exactly at opens_at is allowed (inclusive)
def test_allowed_exactly_at_opening() -> None:
    check_registration(make_event(), OPENS, registered_count=0)


# AC3-B3 (boundary): one second after the window opens is allowed
def test_allowed_one_second_after_opening() -> None:
    check_registration(make_event(), OPENS + ONE_SECOND, registered_count=0)


# AC3-B4 (boundary): one second before the window closes is allowed
def test_allowed_one_second_before_closing() -> None:
    check_registration(make_event(), CLOSES - ONE_SECOND, registered_count=0)


# AC3-B5 (boundary): exactly at closes_at is refused (exclusive, D3)
def test_refused_exactly_at_closing() -> None:
    with pytest.raises(RegistrationNotOpenError):
        check_registration(make_event(), CLOSES, registered_count=0)


# AC3-B6 (boundary): one second after the window closes is refused
def test_refused_one_second_after_closing() -> None:
    with pytest.raises(RegistrationNotOpenError):
        check_registration(make_event(), CLOSES + ONE_SECOND, registered_count=0)


@pytest.mark.parametrize(
    "missing", ["registration_opens_at", "registration_closes_at"]
)
# AC3-N1 (negative): a window with either end unset is not open
def test_unset_window_is_not_open(missing: str) -> None:
    with pytest.raises(RegistrationNotOpenError):
        check_registration(
            make_event(**{missing: None}), INSIDE, registered_count=0
        )


# AC3-X1 (cross-cutting): the decision follows the injected now, not the wall clock
def test_decision_follows_the_injected_clock() -> None:
    event = make_event()
    check_registration(event, datetime(2030, 1, 15, tzinfo=UTC), registered_count=0)
    with pytest.raises(RegistrationNotOpenError):
        check_registration(
            event, datetime(2030, 3, 1, tzinfo=UTC), registered_count=0
        )


# AC3-X1 (cross-cutting): an ISO string window from Supabase behaves like a datetime
def test_iso_string_window_is_understood() -> None:
    event = make_event(
        registration_opens_at="2030-01-10T09:00:00+00:00",
        registration_closes_at="2030-01-20T09:00:00Z",
    )
    check_registration(event, INSIDE, registered_count=0)
    with pytest.raises(RegistrationNotOpenError):
        check_registration(event, CLOSES, registered_count=0)


# AC4-B1 (boundary): one place left is allowed
def test_allowed_with_one_place_left() -> None:
    check_registration(make_event(registration_capacity=5), INSIDE, 4)


# AC4-B2 (boundary): registered equal to capacity is refused as full
def test_refused_when_registered_equals_capacity() -> None:
    with pytest.raises(EventFullError):
        check_registration(make_event(registration_capacity=5), INSIDE, 5)


# AC4-B2 (boundary): registered above capacity (bad data) is still refused
def test_refused_when_registered_exceeds_capacity() -> None:
    with pytest.raises(EventFullError):
        check_registration(make_event(registration_capacity=5), INSIDE, 6)


# AC4-B3 (boundary): capacity 1 allows the first registrant, then no places remain
def test_capacity_of_one_is_used_up_by_the_first_registrant() -> None:
    event = make_event(registration_capacity=1)
    check_registration(event, INSIDE, 0)
    assert places_remaining(event, 0) == 1
    assert places_remaining(event, 1) == 0
    with pytest.raises(EventFullError):
        check_registration(event, INSIDE, 1)


# AC4-N1 (negative): no capacity set means registration is not open
def test_unset_capacity_is_not_open() -> None:
    event = make_event(registration_capacity=None)
    with pytest.raises(RegistrationNotOpenError):
        check_registration(event, INSIDE, registered_count=0)
    assert places_remaining(event, 0) is None


# AC4-B2 (boundary): places_remaining never goes negative
def test_places_remaining_floors_at_zero() -> None:
    assert places_remaining(make_event(registration_capacity=5), 9) == 0


# AC3-N1 / AC4-B2 precedence: a closed window is reported before fullness
def test_window_is_checked_before_capacity() -> None:
    with pytest.raises(RegistrationNotOpenError):
        check_registration(
            make_event(registration_capacity=1), CLOSES + ONE_SECOND, 1
        )
