"""The month availability calendar for one venue (SCRUM-31).

Read-only and detail-free: each slot of each date is one of five states, and
nothing says why or for whom (no block reasons, event names or ids). The state
is derived in the same order the Venue Staff calendar uses, so the two agree:
an active block, then an approved booking, then a slot the venue does not
operate, then a venue blocked in the catalogue, otherwise open.
"""

from __future__ import annotations

import calendar as month_calendar
import datetime as dt
from collections.abc import Iterable
from enum import Enum

from pydantic import BaseModel

from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest, BookingRequestStatus
from app.models import Slot, Venue, VenueStatus
from app.slots import overlaps

SLOT_ORDER = (Slot.AM, Slot.PM, Slot.NIGHT)


class CalendarState(str, Enum):
    OPEN = "open"
    BOOKED = "booked"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"  # the venue is blocked as a whole in the catalogue
    NOT_OFFERED = "not_offered"  # a slot the venue does not operate


class CalendarSlot(BaseModel):
    slot: Slot
    state: CalendarState


class CalendarDay(BaseModel):
    date: dt.date
    slots: list[CalendarSlot]


class VenueCalendar(BaseModel):
    venue_id: str
    month: str
    days: list[CalendarDay]


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """First and last date of a ``YYYY-MM`` month."""

    year, number = (int(part) for part in month.split("-"))
    last = month_calendar.monthrange(year, number)[1]
    return dt.date(year, number, 1), dt.date(year, number, last)


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

    def state(day: dt.date, slot: Slot) -> CalendarState:
        if any(
            overlaps(day, day, [slot], b.start_date, b.end_date, b.slots) for b in active
        ):
            return CalendarState.BLOCKED
        if any(
            overlaps(day, day, [slot], b.start_date, b.end_date, b.slots) for b in held
        ):
            return CalendarState.BOOKED
        if slot not in venue.operating_slots:
            return CalendarState.NOT_OFFERED
        if venue.status != VenueStatus.AVAILABLE:
            return CalendarState.UNAVAILABLE
        return CalendarState.OPEN

    days = []
    for offset in range((last - first).days + 1):
        day = first + dt.timedelta(days=offset)
        days.append(
            CalendarDay(
                date=day,
                slots=[CalendarSlot(slot=slot, state=state(day, slot)) for slot in SLOT_ORDER],
            )
        )
    return VenueCalendar(venue_id=venue.id, month=month, days=days)
