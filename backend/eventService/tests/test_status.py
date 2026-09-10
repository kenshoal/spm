"""Exhaustive unit tests over the pure status state machine.

No FastAPI client, no database — every one of the 10x10 (current, target)
pairs is checked, so "a disallowed transition is refused" is verified for
every pair, not just the happy-path ones.
"""

import itertools

import pytest

from app.status import EventStatus, can_transition, is_terminal

ALL_STATUSES = list(EventStatus)

ALLOWED_FORWARD = {
    (EventStatus.DRAFT, EventStatus.SUBMITTED),
    (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
    (EventStatus.UNDER_REVIEW, EventStatus.CHANGES_REQUESTED),
    (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
    (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
    (EventStatus.CHANGES_REQUESTED, EventStatus.SUBMITTED),
    (EventStatus.APPROVED, EventStatus.PLANNING),
    (EventStatus.PLANNING, EventStatus.CONFIRMED),
    (EventStatus.CONFIRMED, EventStatus.COMPLETED),
}

NON_TERMINAL = {
    EventStatus.DRAFT,
    EventStatus.SUBMITTED,
    EventStatus.UNDER_REVIEW,
    EventStatus.CHANGES_REQUESTED,
    EventStatus.APPROVED,
    EventStatus.PLANNING,
    EventStatus.CONFIRMED,
}

TERMINAL = {EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.REJECTED}


@pytest.mark.parametrize("current,target", sorted(ALLOWED_FORWARD))
def test_allowed_forward_transitions(current: EventStatus, target: EventStatus) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize("current", sorted(NON_TERMINAL))
def test_cancellation_allowed_from_every_non_terminal_status(
    current: EventStatus,
) -> None:
    assert can_transition(current, EventStatus.CANCELLED)


@pytest.mark.parametrize("current", sorted(TERMINAL))
def test_cancellation_refused_from_terminal_status(current: EventStatus) -> None:
    assert not can_transition(current, EventStatus.CANCELLED)


@pytest.mark.parametrize(
    "current,target",
    [
        (c, t)
        for c, t in itertools.product(ALL_STATUSES, ALL_STATUSES)
        if (c, t) not in ALLOWED_FORWARD and t is not EventStatus.CANCELLED
    ],
)
def test_every_other_transition_is_refused(
    current: EventStatus, target: EventStatus
) -> None:
    assert not can_transition(current, target)


@pytest.mark.parametrize("status", sorted(TERMINAL))
def test_terminal_statuses(status: EventStatus) -> None:
    assert is_terminal(status)


@pytest.mark.parametrize("status", sorted(NON_TERMINAL))
def test_non_terminal_statuses(status: EventStatus) -> None:
    assert not is_terminal(status)
