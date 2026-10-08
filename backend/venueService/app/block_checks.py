"""Availability calculations without writes or notifications."""

from collections.abc import Iterable

from app.availability_models import (
    AvailabilityResult,
    BlockConflict,
    BookingOverlap,
    Period,
)
from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest, BookingRequestStatus
from app.models import Venue, VenueStatus
from app.slots import overlaps


def check_availability(
    venue: Venue,
    requested: Period,
    blocks: Iterable[VenueBlock],
    bookings: Iterable[BookingRequest] = (),
) -> AvailabilityResult:
    """Check status, operating slots, active blocks and approved bookings.

    Only approved requests are bookings (0018); pending and rejected ones
    reserve nothing. Callers that check bookings themselves pass none.
    """
    conflicts = [
        BlockConflict(
            block_id=block.id,
            start_date=max(requested.start_date, block.start_date),
            end_date=min(requested.end_date, block.end_date),
            slots=[s for s in requested.slots if s in block.slots],
        )
        for block in blocks
        if block.venue_id == venue.id
        and block.status == BlockStatus.ACTIVE
        and overlaps(
            requested.start_date,
            requested.end_date,
            requested.slots,
            block.start_date,
            block.end_date,
            block.slots,
        )
    ]
    booking_conflicts = [
        BookingOverlap(
            booking_id=booking.id,
            start_date=max(requested.start_date, booking.start_date),
            end_date=min(requested.end_date, booking.end_date),
            slots=[s for s in requested.slots if s in booking.slots],
        )
        for booking in bookings
        if booking.venue_id == venue.id
        and booking.status is BookingRequestStatus.APPROVED
        and overlaps(
            requested.start_date,
            requested.end_date,
            requested.slots,
            booking.start_date,
            booking.end_date,
            booking.slots,
        )
    ]
    unsupported = [s for s in requested.slots if s not in venue.operating_slots]
    reasons = []
    if venue.status != VenueStatus.AVAILABLE:
        reasons.append("venue_unavailable")
    if unsupported:
        reasons.append("outside_operating_slots")
    if conflicts:
        reasons.append("active_block")
    if booking_conflicts:
        reasons.append("booking_conflict")
    return AvailabilityResult(
        venue_id=venue.id,
        available=not reasons,
        reasons=reasons,
        unsupported_slots=unsupported,
        conflicts=conflicts,
        booking_conflicts=booking_conflicts,
    )
