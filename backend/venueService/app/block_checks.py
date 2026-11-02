"""Availability calculations without writes or notifications."""

from collections.abc import Iterable
from datetime import UTC, datetime

from app.availability_models import (
    AvailabilityResult,
    BlockConflict,
    BookingOverlap,
    HoldOverlap,
    Period,
)
from app.block_models import BlockStatus, VenueBlock
from app.booking_models import BookingRequest, BookingRequestStatus
from app.hold_models import VenueHold
from app.models import Venue, VenueStatus
from app.slots import times_overlap
from app.time_conflicts import CLOSE_MINUTE, OPEN_MINUTE, padded_range, window_refusals


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


def _padded_shared(
    requested: Period, padded: tuple[int, int], booking: BookingRequest | VenueHold, venue: Venue
) -> dict:
    """The dates and padded minutes both periods occupy, kept inside 07:00-24:00
    so the overlap is a valid period even when the request's padding is not."""
    start, end = padded_range(
        booking.start_minute, booking.end_minute, venue.setup_minutes, venue.turnaround_minutes
    )
    return {
        "start_date": max(requested.start_date, booking.start_date),
        "end_date": min(requested.end_date, booking.end_date),
        "start_minute": max(padded[0], start, OPEN_MINUTE),
        "end_minute": min(padded[1], end, CLOSE_MINUTE),
    }


def check_availability(
    venue: Venue,
    requested: Period,
    blocks: Iterable[VenueBlock],
    bookings: Iterable[BookingRequest] = (),
    holds: Iterable[VenueHold] = (),
    now: datetime | None = None,
) -> AvailabilityResult:
    """Check venue status, active blocks, the request's setup and turnaround, and
    approved bookings by time.

    Only approved requests are bookings (0018); pending and rejected ones
    reserve nothing. Callers that check bookings themselves pass none. Every
    venue operates 07:00-24:00 (SCRUM-65), which Period already enforces.
    Bookings are compared with setup and turnaround on both sides and blocks
    without, as booking approval does (0054, SCRUM-66). Active, unexpired holds
    (SCRUM-18) take time like bookings; callers leave out a request's own hold.
    """
    conflicts = [
        BlockConflict(block_id=block.id, **_shared(requested, block))
        for block in blocks
        if block.venue_id == venue.id
        and block.status == BlockStatus.ACTIVE
        and _overlaps(requested, block)
    ]
    setup, turnaround = venue.setup_minutes, venue.turnaround_minutes
    padded = padded_range(requested.start_minute, requested.end_minute, setup, turnaround)
    booking_conflicts = [
        BookingOverlap(
            booking_id=booking.id, **_padded_shared(requested, padded, booking, venue)
        )
        for booking in bookings
        if booking.venue_id == venue.id
        and booking.status is BookingRequestStatus.APPROVED
        and times_overlap(
            requested.start_date, requested.end_date, *padded,
            booking.start_date, booking.end_date,
            *padded_range(booking.start_minute, booking.end_minute, setup, turnaround),
        )
    ]
    at = now or datetime.now(UTC)

    def padded_overlap(item: BookingRequest | VenueHold) -> bool:
        return times_overlap(
            requested.start_date, requested.end_date, *padded,
            item.start_date, item.end_date,
            *padded_range(item.start_minute, item.end_minute, setup, turnaround),
        )

    hold_conflicts = [
        HoldOverlap(hold_id=hold.id, **_padded_shared(requested, padded, hold, venue))
        for hold in holds
        if hold.venue_id == venue.id and hold.protects(at) and padded_overlap(hold)
    ]
    reasons = []
    if venue.status != VenueStatus.AVAILABLE:
        reasons.append("venue_unavailable")
    if conflicts:
        reasons.append("active_block")
    reasons.extend(
        window_refusals(requested.start_minute, requested.end_minute, setup, turnaround)
    )
    # SCRUM-30 AC4: the requested time must lie inside the venue's operating hours.
    if not venue.is_open_for(requested.start_minute, requested.end_minute):
        reasons.append("outside_operating_hours")
    if booking_conflicts:
        reasons.append("booking_conflict")
    if hold_conflicts:
        reasons.append("hold_conflict")
    return AvailabilityResult(
        venue_id=venue.id,
        available=not reasons,
        reasons=reasons,
        conflicts=conflicts,
        booking_conflicts=booking_conflicts,
        hold_conflicts=hold_conflicts,
    )
