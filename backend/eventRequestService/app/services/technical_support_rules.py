"""Pure rules for technical support requirements and assignments (SCRUM-19).

These mirror what `record_technical_support_requirement` and
`assign_technical_support_staff` enforce in the database, so the API can
refuse early and the event page can group requirements deterministically.
The database functions stay authoritative: they re-check everything under
the `event_requests` row lock.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.models.event_request import EventRequestStatus

# Support is arranged only once the event has been approved and until it is
# closed: Draft..Rejected refuse, as do the terminal Completed and Cancelled
# (README: venue and equipment work begins only after approval).
SUPPORT_STATUSES = (
    EventRequestStatus.APPROVED,
    EventRequestStatus.PLANNING,
    EventRequestStatus.CONFIRMED,
)

TECHNICAL_SUPPORT_ROLE = "technical_support"


class SupportNotAllowedError(Exception):
    """The event's status does not allow support to be arranged."""

    code = "support_not_allowed"


def ensure_support_allowed(status: EventRequestStatus | str) -> None:
    """Raise unless the event's status allows support work to be arranged."""
    if status not in SUPPORT_STATUSES:
        raise SupportNotAllowedError(
            "Technical support can only be arranged for approved, planning or "
            f"confirmed events, not from {status}"
        )


def is_suitable(
    roles: Iterable[str],
    skill_tags: Iterable[str],
    skill_tag: str,
) -> bool:
    """Suitable means holding the technical_support role AND the requirement's
    tag — one rule for the candidate list and the assign function. No
    availability or double-booking check exists in this slice."""
    return TECHNICAL_SUPPORT_ROLE in set(roles) and skill_tag in set(skill_tags)


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def group_by_requirement(
    requirements: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Pair each requirement with its assignments in the event page's order.

    Requirements order by (recorded_at, id) and staff by (assigned_at, id) —
    the same keys the repository's queries sort by, so equal server timestamps
    cannot reorder rows between reads.
    """
    ordered = sorted(
        requirements,
        key=lambda row: (_as_datetime(row["recorded_at"]), row["id"]),
    )
    by_requirement: dict[str, list[dict[str, Any]]] = {}
    for assignment in sorted(
        assignments,
        key=lambda row: (_as_datetime(row["assigned_at"]), row["id"]),
    ):
        by_requirement.setdefault(assignment["requirement_id"], []).append(
            assignment
        )
    return [
        (requirement, by_requirement.get(requirement["id"], []))
        for requirement in ordered
    ]
