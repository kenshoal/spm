"""SCRUM-22: pure withdrawal rules (AC1-H2, AC1-B1..B4, AC2-P1..P10, AC2-N1, AC2-N10)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services.registration_rules import (
    AlreadyWithdrawnError,
    WithdrawalNotPermittedError,
    check_withdrawal,
)

START = datetime(2030, 2, 1, 18, 0, tzinfo=UTC)
ONE_SECOND = timedelta(seconds=1)
NOW = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)

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
        "status": "Confirmed",
        "proposed_date_times": [START],
        "registration_opens_at": NOW - timedelta(days=5),
        "registration_closes_at": NOW + timedelta(days=5),
        "registration_capacity": 10,
    }
    event.update(overrides)
    return event


def make_registration(**overrides: Any) -> dict[str, Any]:
    registration: dict[str, Any] = {
        "id": "5c1f6c1e-0000-4000-8000-000000000002",
        "status": "Registered",
        "withdrawn_at": None,
    }
    registration.update(overrides)
    return registration


# AC1-B1 (boundary): one second before the event starts, withdrawal is allowed
def test_allowed_one_second_before_start() -> None:
    check_withdrawal(make_event(), make_registration(), START - ONE_SECOND)


# AC1-H2 (happy): allowed after the registration window closed, before the start (D1)
def test_allowed_after_registration_window_closed() -> None:
    event = make_event(registration_closes_at=NOW - timedelta(days=1))
    check_withdrawal(event, make_registration(), NOW)


# AC1-B2 (boundary): exactly at the start, withdrawal is refused
def test_refused_exactly_at_start() -> None:
    with pytest.raises(WithdrawalNotPermittedError):
        check_withdrawal(make_event(), make_registration(), START)


# AC1-B3 (boundary): one second after the start, withdrawal is refused
def test_refused_one_second_after_start() -> None:
    with pytest.raises(WithdrawalNotPermittedError):
        check_withdrawal(make_event(), make_registration(), START + ONE_SECOND)


# AC1-B4 (boundary): a multi-date event is cut off at its earliest date
def test_multi_date_event_uses_earliest_date() -> None:
    event = make_event(
        proposed_date_times=[START + timedelta(days=2), START]
    )
    with pytest.raises(WithdrawalNotPermittedError):
        check_withdrawal(event, make_registration(), START + timedelta(days=1))


# AC1-B4 (boundary): ISO strings from the Data API are read as datetimes
def test_accepts_iso_string_dates() -> None:
    event = make_event(proposed_date_times=[START.isoformat()])
    check_withdrawal(event, make_registration(), START - ONE_SECOND)
    with pytest.raises(WithdrawalNotPermittedError):
        check_withdrawal(event, make_registration(), START)


# AC2-N10 (negative): an event with no dates has no start, so nothing is withdrawable
def test_refused_when_event_has_no_dates() -> None:
    with pytest.raises(WithdrawalNotPermittedError):
        check_withdrawal(
            make_event(proposed_date_times=[]), make_registration(), NOW
        )


# AC2-P1 (partition): one representative per non-Confirmed status is refused
@pytest.mark.parametrize("status", NON_CONFIRMED)
def test_refused_for_non_confirmed_event(status: str) -> None:
    with pytest.raises(WithdrawalNotPermittedError):
        check_withdrawal(make_event(status=status), make_registration(), NOW)


# AC2-N1 (negative): an already withdrawn registration is reported as such
def test_refused_when_already_withdrawn() -> None:
    registration = make_registration(status="Withdrawn", withdrawn_at=NOW)
    with pytest.raises(AlreadyWithdrawnError):
        check_withdrawal(make_event(), registration, NOW)


# AC2-N1 (negative): already withdrawn wins over a started event (mirrors the DB order)
def test_already_withdrawn_reported_before_not_permitted() -> None:
    registration = make_registration(status="Withdrawn", withdrawn_at=NOW)
    with pytest.raises(AlreadyWithdrawnError):
        check_withdrawal(make_event(), registration, START + ONE_SECOND)
