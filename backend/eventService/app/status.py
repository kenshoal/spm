"""Pure event-status state machine.

No FastAPI, no database access — kept dependency-free so every allowed and
disallowed transition can be unit-tested directly, without a client or a DB.
"""

from enum import StrEnum


class EventStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    PLANNING = "planning"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# Forward workflow transitions. Cancellation is deliberately not listed here:
# it can be reached from any non-terminal status, not just one, so it is
# handled as a cross-cutting rule in can_transition() instead.
_ALLOWED_TRANSITIONS: dict[EventStatus, frozenset[EventStatus]] = {
    EventStatus.DRAFT: frozenset({EventStatus.SUBMITTED}),
    EventStatus.SUBMITTED: frozenset({EventStatus.UNDER_REVIEW}),
    EventStatus.UNDER_REVIEW: frozenset(
        {
            EventStatus.CHANGES_REQUESTED,
            EventStatus.APPROVED,
            EventStatus.REJECTED,
        }
    ),
    EventStatus.CHANGES_REQUESTED: frozenset({EventStatus.SUBMITTED}),
    EventStatus.APPROVED: frozenset({EventStatus.PLANNING}),
    EventStatus.PLANNING: frozenset({EventStatus.CONFIRMED}),
    EventStatus.CONFIRMED: frozenset({EventStatus.COMPLETED}),
    EventStatus.COMPLETED: frozenset(),
    EventStatus.CANCELLED: frozenset(),
    EventStatus.REJECTED: frozenset(),
}

TERMINAL_STATUSES: frozenset[EventStatus] = frozenset(
    {EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.REJECTED}
)


def is_terminal(status: EventStatus) -> bool:
    return status in TERMINAL_STATUSES


def can_transition(current: EventStatus, target: EventStatus) -> bool:
    """Whether `current -> target` is an allowed status transition.

    Cancellation is allowed from any non-terminal status regardless of the
    forward-workflow map; every other transition must appear in it.
    """
    if target is EventStatus.CANCELLED:
        return not is_terminal(current)
    return target in _ALLOWED_TRANSITIONS[current]
