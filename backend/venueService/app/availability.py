"""Availability against venue blocks and approved bookings (SCRUM-15)."""

from collections.abc import Iterable
from datetime import date

from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest, BookingRequestStatus
from app.models import Slot, Venue, VenueStatus
from app.slots import overlaps


def available_slots(
    venue: Venue,
    on_date: date,
    blocks: Iterable[VenueBlock],
    bookings: Iterable[BookingRequest] = (),
) -> list[Slot]:
    """Return operating slots free of active blocks and approved bookings."""
    if venue.status != VenueStatus.AVAILABLE:
        return []
    taken = [
        (block.start_date, block.end_date, block.slots)
        for block in blocks
        if block.venue_id == venue.id and block.status == BlockStatus.ACTIVE
    ] + [
        (booking.start_date, booking.end_date, booking.slots)
        for booking in bookings
        if booking.venue_id == venue.id
        and booking.status is BookingRequestStatus.APPROVED
    ]
    return [
        slot
        for slot in venue.operating_slots
        if not any(
            overlaps(on_date, on_date, [slot], start, end, slots)
            for start, end, slots in taken
        )
    ]
