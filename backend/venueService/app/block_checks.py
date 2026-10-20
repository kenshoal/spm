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
from app.slots import times_overlap


def _overlaps(requested: Period, item: VenueBlock | BookingRequest) -> bool:
    return times_overlap(
        requested.start_date, requested.end_date,
        requested.start_minute, requested.end_minute,
        item.start_date, item.end_date, item.start_minute, item.end_minute,
    )


def _shared(requested: Period, item: VenueBlock | BookingRequest) -> dict:
    """The dates and times both periods cover."""
    return {
        "start_date": max(requested.start_date, item.start_date),
        "end_date": min(requested.end_date, item.end_date),
        "start_minute": max(requested.start_minute, item.start_minute),
        "end_minute": min(requested.end_minute, item.end_minute),
    }


def check_availability(
    venue: Venue,
    requested: Period,
    blocks: Iterable[VenueBlock],
    bookings: Iterable[BookingRequest] = (),
) -> AvailabilityResult:
    """Check venue status, active blocks and approved bookings by time.

    Only approved requests are bookings (0018); pending and rejected ones
    reserve nothing. Callers that check bookings themselves pass none. Every
    venue operates 07:00-24:00 (SCRUM-65), which Period already enforces.
    """
    conflicts = [
        BlockConflict(block_id=block.id, **_shared(requested, block))
        for block in blocks
        if block.venue_id == venue.id
        and block.status == BlockStatus.ACTIVE
        and _overlaps(requested, block)
    ]
    booking_conflicts = [
        BookingOverlap(booking_id=booking.id, **_shared(requested, booking))
        for booking in bookings
        if booking.venue_id == venue.id
        and booking.status is BookingRequestStatus.APPROVED
        and _overlaps(requested, booking)
    ]
    reasons = []
    if venue.status != VenueStatus.AVAILABLE:
        reasons.append("venue_unavailable")
    if conflicts:
        reasons.append("active_block")
    if booking_conflicts:
        reasons.append("booking_conflict")
    return AvailabilityResult(
        venue_id=venue.id,
        available=not reasons,
        reasons=reasons,
        conflicts=conflicts,
        booking_conflicts=booking_conflicts,
    )
