"""Dated availability for venue search (SCRUM-15, SCRUM-65, SCRUM-66).

A venue is free for a time when it is available, no active block overlaps the
time, the time's setup and turnaround fit 07:00-24:00 and no approved booking's
padded range overlaps the time's padded range. That is booking approval's rule
(0054), so search never offers a time that approval would refuse. Blocks are
compared without padding, as approval does.
"""

from collections.abc import Iterable
from datetime import date

from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest
from app.models import Venue, VenueStatus
from app.slots import times_overlap
from app.time_conflicts import (
    CLOSE_MINUTE,
    OPEN_MINUTE,
    STEP_MINUTES,
    padded_booked_ranges,
    padded_range,
    window_refusals,
)


def _free_at(
    venue: Venue,
    on_date: date,
    start_minute: int,
    end_minute: int,
    blocked: list[tuple[date, date, int, int]],
    booked: list[tuple[date, date, int, int]],
) -> bool:
    setup, turnaround = venue.setup_minutes, venue.turnaround_minutes
    if window_refusals(start_minute, end_minute, setup, turnaround):
        return False
    padded = padded_range(start_minute, end_minute, setup, turnaround)
    return not any(
        times_overlap(on_date, on_date, start_minute, end_minute, *item) for item in blocked
    ) and not any(times_overlap(on_date, on_date, *padded, *item) for item in booked)


def is_free(
    venue: Venue,
    on_date: date,
    start_minute: int | None,
    end_minute: int | None,
    blocks: Iterable[VenueBlock],
    bookings: Iterable[BookingRequest] = (),
) -> bool:
    """Whether the venue is free at that time on that date, or, without a time,
    whether some 15-minute booking that day would be accepted."""
    if venue.status != VenueStatus.AVAILABLE:
        return False
    blocked = [
        (b.start_date, b.end_date, b.start_minute, b.end_minute)
        for b in blocks
        if b.venue_id == venue.id and b.status == BlockStatus.ACTIVE
    ]
    booked = padded_booked_ranges(venue, bookings)
    if start_minute is None or end_minute is None:
        return any(
            _free_at(venue, on_date, start, start + STEP_MINUTES, blocked, booked)
            for start in range(OPEN_MINUTE, CLOSE_MINUTE, STEP_MINUTES)
        )
    return _free_at(venue, on_date, start_minute, end_minute, blocked, booked)
