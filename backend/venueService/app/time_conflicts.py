"""Venue booking conflict rules on 15-minute time ranges (SCRUM-20).

Pure functions with no storage or HTTP. A booking follows SCRUM-65's model
(0050): an inclusive date range with one start and end minute applied on each
date, in minutes after midnight so that 24:00 is representable. Two bookings
clash only if their date ranges share a day and their padded times overlap. Times fall on 15-minute steps inside the 07:00-24:00 operating
window (discussion #131). A booking occupies its venue from start minus setup to
end plus turnaround (SCRUM-59; Week 7 Change #1), and that padding must also
stay inside the window (Product Owner, 20 October 2026). Ranges are half-open,
so a range ending at 12:00 and one starting at 12:00 do not overlap. Only
approved bookings conflict.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from itertools import combinations

from app.models import Venue

STEP_MINUTES = 15
OPEN_MINUTE = 7 * 60
CLOSE_MINUTE = 24 * 60
# Compared by value, so booking_models can import this module without a cycle.
APPROVED = "approved"


class BookingTimeError(ValueError):
    """A booking time breaks a rule. ``code`` names the rule for API callers."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TimedBooking:
    """The fields of a booking the conflict rules need (BookingRequest's names)."""

    id: str
    venue_id: str
    start_date: date
    end_date: date
    start_minute: int
    end_minute: int
    status: str


def padded_range(start: int, end: int, setup: int, turnaround: int) -> tuple[int, int]:
    """The minutes a booking occupies its venue, including setup and turnaround."""
    return start - setup, end + turnaround


def check_booking_time(start: int, end: int, setup: int = 0, turnaround: int = 0) -> None:
    """Raise BookingTimeError unless the booking and its padding fit the rules."""
    if start % STEP_MINUTES or end % STEP_MINUTES:
        raise BookingTimeError("off_step", "Times must be on a 15-minute step.")
    if start < OPEN_MINUTE or end > CLOSE_MINUTE:
        raise BookingTimeError(
            "outside_operating_window", "Bookings must fall between 07:00 and 24:00."
        )
    if end <= start:
        raise BookingTimeError("end_not_after_start", "The end must be after the start.")
    padded_start, padded_end = padded_range(start, end, setup, turnaround)
    if padded_start < OPEN_MINUTE:
        raise BookingTimeError(
            "setup_outside_window", "The venue's setup time would start before 07:00."
        )
    if padded_end > CLOSE_MINUTE:
        raise BookingTimeError(
            "turnaround_outside_window",
            "The venue's turnaround time would end after 24:00.",
        )


def window_refusals(start: int, end: int, setup: int, turnaround: int) -> list[str]:
    """The padding codes for a booking time, in approval's order (0054): empty
    when its setup and turnaround fit 07:00-24:00."""
    padded_start, padded_end = padded_range(start, end, setup, turnaround)
    codes = []
    if padded_start < OPEN_MINUTE:
        codes.append("setup_outside_window")
    if padded_end > CLOSE_MINUTE:
        codes.append("turnaround_outside_window")
    return codes


def padded_booked_ranges(
    venue: Venue, bookings: Iterable[object]
) -> list[tuple[date, date, int, int]]:
    """Approved bookings at the venue as the dates and minutes each occupies,
    setup and turnaround included (SCRUM-66). Search, availability and the
    calendar treat these as taken, as booking approval does (0054)."""
    setup, turnaround = venue.setup_minutes, venue.turnaround_minutes
    return [
        (
            booking.start_date,
            booking.end_date,
            *padded_range(booking.start_minute, booking.end_minute, setup, turnaround),
        )
        for booking in bookings
        if booking.status == APPROVED and booking.venue_id == venue.id
    ]


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _share_a_day(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def _padded(booking: TimedBooking, setup: int, turnaround: int) -> tuple[int, int]:
    return padded_range(booking.start_minute, booking.end_minute, setup, turnaround)


def _order(booking: TimedBooking) -> tuple[date, int, str]:
    return booking.start_date, booking.start_minute, booking.id


def find_conflicts(
    venue: Venue,
    start_date: date,
    end_date: date,
    start_minute: int,
    end_minute: int,
    bookings: Iterable[TimedBooking],
    *,
    exclude_id: str | None = None,
) -> list[TimedBooking]:
    """Approved bookings at the venue that share a day with the request and whose
    padded times overlap the padded request, in start order.

    Pass ``exclude_id`` when checking a reschedule, so a booking is never compared
    with itself.
    """
    setup, turnaround = venue.setup_minutes, venue.turnaround_minutes
    wanted = padded_range(start_minute, end_minute, setup, turnaround)
    return sorted(
        (
            booking
            for booking in bookings
            if booking.status == APPROVED
            and booking.venue_id == venue.id
            and booking.id != exclude_id
            and _share_a_day(start_date, end_date, booking.start_date, booking.end_date)
            and _overlaps(wanted, _padded(booking, setup, turnaround))
        ),
        key=_order,
    )


def _outside_window(booking: TimedBooking, setup: int, turnaround: int) -> bool:
    padded_start, padded_end = _padded(booking, setup, turnaround)
    return padded_start < OPEN_MINUTE or padded_end > CLOSE_MINUTE


def _pair_conflicts(
    a: TimedBooking, b: TimedBooking, setup: int, turnaround: int
) -> bool:
    return _share_a_day(a.start_date, a.end_date, b.start_date, b.end_date) and (
        _overlaps(_padded(a, setup, turnaround), _padded(b, setup, turnaround))
    )


def affected_by_timing_change(
    venue_id: str,
    bookings: Iterable[TimedBooking],
    old: tuple[int, int],
    new: tuple[int, int],
    today: date,
) -> list[TimedBooking]:
    """Bookings to flag for review after a venue's (setup, turnaround) change.

    Considers approved bookings at the venue that have not ended (end date on or
    after ``today``). Returns both bookings of each pair that conflicts under the
    new times but did not under the old, plus any booking whose padding falls
    outside the window under the new times but did not under the old. An
    unchanged save returns nothing.
    """
    if old == new:
        return []
    current = [
        booking
        for booking in bookings
        if booking.status == APPROVED
        and booking.venue_id == venue_id
        and booking.end_date >= today
    ]
    affected: dict[str, TimedBooking] = {}
    for booking in current:
        if _outside_window(booking, *new) and not _outside_window(booking, *old):
            affected[booking.id] = booking
    for a, b in combinations(current, 2):
        if _pair_conflicts(a, b, *new) and not _pair_conflicts(a, b, *old):
            affected[a.id] = a
            affected[b.id] = b
    return sorted(affected.values(), key=_order)
