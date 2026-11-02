"""Dated availability for venue search (SCRUM-15, SCRUM-65, SCRUM-66).

A venue is free for a time when it is available, no active block overlaps the
time, the time's setup and turnaround fit 07:00-24:00, the time lies inside the venue's own
operating hours (SCRUM-30 AC4) and no approved booking's
padded range overlaps the time's padded range. That is booking approval's rule
(0054), so search never offers a time that approval would refuse. Blocks are
compared without padding, as approval does. Active, unexpired holds (SCRUM-18)
take time like approved bookings.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime

from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest
from app.hold_models import VenueHold
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
    # SCRUM-30 AC4: time outside the venue's operating hours is never free.
    if not venue.is_open_for(start_minute, end_minute):
        return False
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
    holds: Iterable[VenueHold] = (),
    now: datetime | None = None,
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
    at = now or datetime.now(UTC)
    booked = padded_booked_ranges(venue, bookings) + [
        (h.start_date, h.end_date, *padded_range(
            h.start_minute, h.end_minute, venue.setup_minutes, venue.turnaround_minutes,
        ))
        for h in holds
        if h.venue_id == venue.id and h.protects(at)
    ]
    if start_minute is None or end_minute is None:
        return any(
            _free_at(venue, on_date, start, start + STEP_MINUTES, blocked, booked)
            for start in range(
                max(OPEN_MINUTE, venue.operating_start_minute),
                min(CLOSE_MINUTE, venue.operating_end_minute),
                STEP_MINUTES,
            )
        )
    return _free_at(venue, on_date, start_minute, end_minute, blocked, booked)
