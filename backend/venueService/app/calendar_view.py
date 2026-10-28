"""The month availability calendar for one venue (SCRUM-31, on times by SCRUM-69).

Read-only and detail-free: each date lists the times that are booked or blocked
and the times that are free, and nothing says why or for whom (no block
reasons, event names or ids). Times are minutes after midnight in 15-minute
steps inside the 07:00-24:00 operating window, as for bookings (SCRUM-65).

Each date is a partition of the window: ``entries`` and ``free`` are ordered,
never overlap, and together cover exactly 07:00-24:00. Ranges are half-open, so
a booking ending at 12:00 leaves 12:00 free. Where a block overlaps a booking
the overlap is blocked and the booking is split around it, the same order the
Venue Staff calendar uses (an active block, then an approved booking). Touching
ranges of one state are merged, so the boundary between two events never shows.
A venue blocked in the catalogue marks every date ``unavailable`` and has no
free time; its blocks and bookings are still listed.
"""

from __future__ import annotations

import calendar as month_calendar
import datetime as dt
from collections.abc import Iterable
from enum import Enum

from pydantic import BaseModel

from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest, BookingRequestStatus
from app.models import Venue, VenueStatus
from app.time_conflicts import CLOSE_MINUTE, OPEN_MINUTE, padded_range

Minutes = tuple[int, int]


class CalendarState(str, Enum):
    BOOKED = "booked"
    BLOCKED = "blocked"


class CalendarEntry(BaseModel):
    state: CalendarState
    start_minute: int
    end_minute: int


class CalendarRange(BaseModel):
    start_minute: int
    end_minute: int


class CalendarDay(BaseModel):
    date: dt.date
    unavailable: bool  # the venue is blocked as a whole in the catalogue
    entries: list[CalendarEntry]
    free: list[CalendarRange]


class VenueCalendar(BaseModel):
    venue_id: str
    month: str
    days: list[CalendarDay]


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """First and last date of a ``YYYY-MM`` month."""

    year, number = (int(part) for part in month.split("-"))
    last = month_calendar.monthrange(year, number)[1]
    return dt.date(year, number, 1), dt.date(year, number, last)


def occupied_minutes(venue: Venue, booking: BookingRequest) -> Minutes:
    """The minutes a booking holds its venue on each of its dates.

    The booked time widened by the venue's setup and turnaround (SCRUM-66), the
    same rule booking approval (0054) and search use. The caller clips the
    result to 07:00-24:00.
    """

    return padded_range(
        booking.start_minute, booking.end_minute, venue.setup_minutes, venue.turnaround_minutes
    )


def _clip(start: int, end: int) -> Minutes | None:
    start, end = max(start, OPEN_MINUTE), min(end, CLOSE_MINUTE)
    return (start, end) if start < end else None


def _merge(ranges: Iterable[Minutes]) -> list[Minutes]:
    """Sort ranges and join those that overlap or touch."""

    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _subtract(ranges: list[Minutes], cuts: list[Minutes]) -> list[Minutes]:
    """The parts of ``ranges`` that no range in ``cuts`` covers."""

    remaining: list[Minutes] = []
    for start, end in ranges:
        cursor = start
        for cut_start, cut_end in cuts:
            if cut_end <= cursor or cut_start >= end:
                continue
            if cut_start > cursor:
                remaining.append((cursor, cut_start))
            cursor = max(cursor, cut_end)
        if cursor < end:
            remaining.append((cursor, end))
    return remaining


def build_calendar(
    venue: Venue,
    month: str,
    blocks: Iterable[VenueBlock],
    bookings: Iterable[BookingRequest],
) -> VenueCalendar:
    first, last = month_bounds(month)
    active = [
        block
        for block in blocks
        if block.venue_id == venue.id and block.status == BlockStatus.ACTIVE
    ]
    held = [
        booking
        for booking in bookings
        if booking.venue_id == venue.id
        and booking.status is BookingRequestStatus.APPROVED
    ]
    unavailable = venue.status != VenueStatus.AVAILABLE

    days = []
    for offset in range((last - first).days + 1):
        date = first + dt.timedelta(days=offset)
        blocked = _merge(
            clipped
            for block in active
            if block.start_date <= date <= block.end_date
            if (clipped := _clip(block.start_minute, block.end_minute))
        )
        booked = _subtract(
            _merge(
                clipped
                for booking in held
                if booking.start_date <= date <= booking.end_date
                if (clipped := _clip(*occupied_minutes(venue, booking)))
            ),
            blocked,
        )
        entries = sorted(
            [(CalendarState.BLOCKED, start, end) for start, end in blocked]
            + [(CalendarState.BOOKED, start, end) for start, end in booked],
            key=lambda item: item[1],
        )
        free = (
            []
            if unavailable
            else _subtract([(OPEN_MINUTE, CLOSE_MINUTE)], _merge(blocked + booked))
        )
        days.append(
            CalendarDay(
                date=date,
                unavailable=unavailable,
                entries=[
                    CalendarEntry(state=state, start_minute=start, end_minute=end)
                    for state, start, end in entries
                ],
                free=[CalendarRange(start_minute=start, end_minute=end) for start, end in free],
            )
        )
    return VenueCalendar(venue_id=venue.id, month=month, days=days)
