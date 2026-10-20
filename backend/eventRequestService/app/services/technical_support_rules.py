"""Pure rules for technical support requirements and assignments (SCRUM-19).

These mirror what `record_technical_support_requirement` and
`assign_technical_support_staff` enforce in the database, so the API can
refuse early and the event page can group requirements deterministically.
The database functions stay authoritative: they re-check everything under
the `event_requests` row lock.
"""

from typing import Any


class SupportNotAllowedError(Exception):
    """The event's status does not allow support to be arranged."""


def ensure_support_allowed(status: Any) -> None:
    raise NotImplementedError


def is_suitable(
    roles: Any,
    skill_tags: Any,
    skill_tag: Any,
) -> bool:
    raise NotImplementedError


def group_by_requirement(
    requirements: Any,
    assignments: Any,
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    raise NotImplementedError
