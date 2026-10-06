"""Availability calculations without writes or notifications."""

from collections.abc import Iterable

from app.availability_models import AvailabilityResult, BlockConflict, Period
from app.block_models import BlockStatus, VenueBlock
from app.models import Venue, VenueStatus
from app.slots import overlaps


def check_availability(
    venue: Venue, requested: Period, blocks: Iterable[VenueBlock]
) -> AvailabilityResult:
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
    unsupported = [s for s in requested.slots if s not in venue.operating_slots]
    reasons = []
    if venue.status != VenueStatus.AVAILABLE:
        reasons.append("venue_unavailable")
    if unsupported:
        reasons.append("outside_operating_slots")
    if conflicts:
        reasons.append("active_block")
    return AvailabilityResult(
        venue_id=venue.id,
        available=not reasons,
        reasons=reasons,
        unsupported_slots=unsupported,
        conflicts=conflicts,
    )
