"""Dated availability for venue search (SCRUM-15, SCRUM-65)."""

from collections.abc import Iterable
from datetime import date

from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest, BookingRequestStatus
from app.models import Venue, VenueStatus
from app.slots import has_free_time, times_overlap


def _taken(
    venue: Venue, blocks: Iterable[VenueBlock], bookings: Iterable[BookingRequest]
) -> list[tuple[date, date, int, int]]:
    return [
        (item.start_date, item.end_date, item.start_minute, item.end_minute)
        for item in [
            *(b for b in blocks if b.status == BlockStatus.ACTIVE),
            *(b for b in bookings if b.status is BookingRequestStatus.APPROVED),
        ]
        if item.venue_id == venue.id
    ]


def is_free(
    venue: Venue,
    on_date: date,
    start_minute: int | None,
    end_minute: int | None,
    blocks: Iterable[VenueBlock],
    bookings: Iterable[BookingRequest] = (),
) -> bool:
    """Whether the venue is free at that time on that date, or, without a time,
    free for at least part of 07:00-24:00 that day."""
    if venue.status != VenueStatus.AVAILABLE:
        return False
    taken = _taken(venue, blocks, bookings)
    if start_minute is None or end_minute is None:
        return has_free_time(on_date, taken)
    return not any(
        times_overlap(on_date, on_date, start_minute, end_minute, *item) for item in taken
    )
