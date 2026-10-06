"""Availability against venue blocks; reservations are integrated separately."""

from collections.abc import Iterable
from datetime import date

from app.block_models import BlockStatus, VenueBlock
from app.models import Slot, Venue, VenueStatus
from app.slots import overlaps


def available_slots(
    venue: Venue, on_date: date, blocks: Iterable[VenueBlock]
) -> list[Slot]:
    """Return operating slots unaffected by active blocks on this date."""
    if venue.status != VenueStatus.AVAILABLE:
        return []
    active_blocks = [
        block
        for block in blocks
        if block.venue_id == venue.id and block.status == BlockStatus.ACTIVE
    ]
    return [
        slot
        for slot in venue.operating_slots
        if not any(
            overlaps(
                on_date,
                on_date,
                [slot],
                block.start_date,
                block.end_date,
                block.slots,
            )
            for block in active_blocks
        )
    ]
