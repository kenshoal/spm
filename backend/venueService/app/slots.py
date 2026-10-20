"""Pure inclusive date-range × slot comparisons using the catalogue's Slot.

Selected slots repeat on every date in each range; NIGHT belongs to its starting
date. Callers handle venue identity, active/confirmed status, and side effects.
Irregular daily schedules must be compared as separate periods.
"""

from collections.abc import Collection, Iterable
from datetime import date, timedelta

from pydantic_core import PydanticCustomError

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


# SCRUM-65: slot time ranges in minutes after midnight (Product Owner, 20 October
# 2026). They leave no gaps, so consecutive slots join into one exact range.
SLOT_RANGES = {Slot.AM: (420, 720), Slot.PM: (720, 1080), Slot.NIGHT: (1080, 1440)}


def slots_to_range(slots: Collection[Slot | str]) -> tuple[int, int]:
    """The one time range covered by consecutive slots (the booking conversion)."""
    chosen = [slot for slot in SLOT_RANGES if slot in {Slot(s) for s in slots}]
    if not chosen:
        raise ValueError("At least one slot is needed")
    start, end = SLOT_RANGES[chosen[0]][0], SLOT_RANGES[chosen[-1]][1]
    if sum(b - a for a, b in (SLOT_RANGES[s] for s in chosen)) != end - start:
        raise ValueError("Slots must be consecutive to become one time range")
    return start, end


def touched_slots(start_minute: int, end_minute: int) -> list[Slot]:
    """Slots that a half-open time range overlaps, for slot-based readers."""
    return [
        slot
        for slot, (slot_start, slot_end) in SLOT_RANGES.items()
        if start_minute < slot_end and slot_start < end_minute
    ]


def times_overlap(
    a_start: date, a_end: date, a_from: int, a_to: int,
    b_start: date, b_end: date, b_from: int, b_to: int,
) -> bool:
    """Whether two date ranges share a day and their daily time ranges overlap."""
    return a_start <= b_end and b_start <= a_end and a_from < b_to and b_from < a_to


OPEN_MINUTE, CLOSE_MINUTE, STEP_MINUTES = 420, 1440, 15


def check_time_range(start_minute: int, end_minute: int) -> None:
    """Raise a 422-ready error unless a range is on 15-minute steps within
    07:00-24:00 and ends after it starts. The codes match SCRUM-20's
    check_booking_time; the database checks the same rules (0050, 0051)."""
    if start_minute % STEP_MINUTES or end_minute % STEP_MINUTES:
        raise PydanticCustomError("off_step", "Times must be on a 15-minute step.")
    if start_minute < OPEN_MINUTE or end_minute > CLOSE_MINUTE:
        raise PydanticCustomError(
            "outside_operating_window", "Times must fall between 07:00 and 24:00."
        )
    if end_minute <= start_minute:
        raise PydanticCustomError("end_not_after_start", "The end must be after the start.")


def has_free_time(on_date: date, taken: Iterable[tuple[date, date, int, int]]) -> bool:
    """Whether any of 07:00-24:00 on a date is outside the taken ranges."""
    covered = OPEN_MINUTE
    for start, end in sorted(
        (a_from, a_to)
        for first, last, a_from, a_to in taken
        if first <= on_date <= last
    ):
        if start > covered:
            return True
        covered = max(covered, end)
    return covered < CLOSE_MINUTE
