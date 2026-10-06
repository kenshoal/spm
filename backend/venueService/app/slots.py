"""Pure inclusive date-range × slot comparisons using the catalogue's Slot.

Selected slots repeat on every date in each range; NIGHT belongs to its starting
date. Callers handle venue identity, active/confirmed status, and side effects.
Irregular daily schedules must be compared as separate periods.
"""

from collections.abc import Collection
from datetime import date, timedelta

from app.models import Slot


def _validate_dates(a_start: date, a_end: date, b_start: date, b_end: date) -> None:
    if a_end < a_start or b_end < b_start:
        raise ValueError("Each end date must be on or after its start date")


def overlaps(
    a_start: date,
    a_end: date,
    a_slots: Collection[Slot],
    b_start: date,
    b_end: date,
    b_slots: Collection[Slot],
) -> bool:
    """Whether periods share a date and slot, without enumerating dates.

    Reversed ranges raise ValueError. An empty slot collection occupies no slots.
    Creation payloads separately reject empty or duplicate slots via their schema.
    """
    _validate_dates(a_start, a_end, b_start, b_end)
    return (
        a_start <= b_end
        and b_start <= a_end
        and bool(set(a_slots).intersection(b_slots))
    )


def conflicts(
    a_start: date,
    a_end: date,
    a_slots: Collection[Slot],
    b_start: date,
    b_end: date,
    b_slots: Collection[Slot],
) -> list[tuple[date, Slot]]:
    """Unique shared pairs ordered by date, then AM, PM, NIGHT.

    Reversed ranges raise ValueError. Disjoint dates or slots return an empty list.
    This enumerates the intersection; callers should use overlaps() for yes/no
    checks and restrict periods to the display window for calendar rendering.
    """
    _validate_dates(a_start, a_end, b_start, b_end)
    start, end = max(a_start, b_start), min(a_end, b_end)
    shared = set(a_slots).intersection(b_slots)
    if start > end or not shared:
        return []
    ordered = [slot for slot in (Slot.AM, Slot.PM, Slot.NIGHT) if slot in shared]
    return [
        (start + timedelta(days=offset), slot)
        for offset in range((end - start).days + 1)
        for slot in ordered
    ]
