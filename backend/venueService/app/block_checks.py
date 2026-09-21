"""Availability and event-impact calculations without writes or notifications."""

from collections.abc import Iterable
from datetime import date

from fastapi import HTTPException

from app.availability_models import (
    AffectedEvent,
    AffectedPeriod,
    AvailabilityResult,
    BlockConflict,
    EventAllocation,
    Period,
)
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


def find_affected_events(
    block: VenueBlock, allocations: Iterable[EventAllocation], today: date
) -> list[AffectedEvent]:
    if block.status != BlockStatus.ACTIVE or block.end_date < today:
        return []
    events: dict[str, AffectedEvent] = {}
    seen: dict[str, EventAllocation] = {}
    for allocation in allocations:
        if allocation.venue_id != block.venue_id:
            continue
        previous = seen.get(allocation.allocation_id)
        if previous is not None:
            if previous != allocation:
                raise HTTPException(
                    502, "Event allocation lookup returned inconsistent data"
                )
            continue
        seen[allocation.allocation_id] = allocation
        if (
            allocation.allocation_status != "active"
            or allocation.event_status != "Confirmed"
        ):
            continue
        if allocation.end_date < today or not overlaps(
            block.start_date,
            block.end_date,
            block.slots,
            allocation.start_date,
            allocation.end_date,
            allocation.slots,
        ):
            continue
        affected = events.get(allocation.event_request_id)
        if affected is None:
            affected = AffectedEvent(
                event_request_id=allocation.event_request_id,
                event_name=allocation.event_name,
                coordinator_id=allocation.coordinator_id,
                affected_periods=[],
            )
            events[allocation.event_request_id] = affected
        elif affected.coordinator_id != allocation.coordinator_id:
            raise HTTPException(
                502, "Event allocation lookup returned inconsistent data"
            )
        affected.affected_periods.append(
            AffectedPeriod(
                allocation_id=allocation.allocation_id,
                start_date=max(block.start_date, allocation.start_date, today),
                end_date=min(block.end_date, allocation.end_date),
                slots=[s for s in block.slots if s in allocation.slots],
            )
        )
    return list(events.values())
