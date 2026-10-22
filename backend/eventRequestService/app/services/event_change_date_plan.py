"""Pure date-only booking plans; this module does not persist or approve changes."""

from copy import deepcopy
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

_SINGAPORE = ZoneInfo("Asia/Singapore")


class DateReschedulePlanError(ValueError):
    """A date proposal cannot be mapped onto existing booking dates safely."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def plan_date_only_reschedule(
    old_dates: list[str],
    new_dates: list[str],
    bookings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return proposed booking rows without changing inputs or stored state."""
    if not old_dates or not new_dates or len(old_dates) != len(new_dates):
        raise DateReschedulePlanError("unsupported_date_mapping")

    try:
        old_anchors = [_singapore_anchor(value) for value in old_dates]
        new_anchors = [_singapore_anchor(value) for value in new_dates]
        shift = new_anchors[0].date() - old_anchors[0].date()
        # Compare corresponding anchors, rather than sorting or guessing which
        # event date belongs to a booking. Every anchor must describe one shift.
        for old, new in zip(old_anchors, new_anchors, strict=True):
            if new.time() != old.time() or new.date() - old.date() != shift:
                raise DateReschedulePlanError("unsupported_date_mapping")
        if not shift.days:
            raise DateReschedulePlanError("no_op_date_mapping")

        planned = []
        for booking in bookings:
            if booking.get("status") not in {"pending", "approved"}:
                continue
            candidate = deepcopy(booking)
            for field in ("start_date", "end_date"):
                candidate[field] = (date.fromisoformat(booking[field]) + shift).isoformat()
            planned.append(candidate)
        return planned
    except DateReschedulePlanError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise DateReschedulePlanError("unsupported_date_mapping") from error


def _singapore_anchor(value: str) -> datetime:
    anchor = datetime.fromisoformat(value)
    if anchor.utcoffset() is None:
        raise DateReschedulePlanError("unsupported_date_mapping")
    return anchor.astimezone(_SINGAPORE)
