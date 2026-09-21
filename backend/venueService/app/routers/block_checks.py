"""Read-only interfaces for booking callers and future notification workflows."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from app.availability_models import AffectedEvent, AvailabilityResult, Period
from app.block_checks import check_availability, find_affected_events
from app.block_models import BlockStatus
from app.event_allocations import EventAllocationSource, get_event_allocations
from app.routers.venues import AuthenticatedDep, BlockRepoDep, RepoDep, VenueStaffDep

router = APIRouter(prefix="/venues", tags=["venue block checks"])


def current_venue_date() -> date:
    return datetime.now(ZoneInfo("Asia/Singapore")).date()


@router.post("/{venue_id}/availability", response_model=AvailabilityResult)
def availability(
    venue_id: str,
    payload: Period,
    principal: AuthenticatedDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
) -> AvailabilityResult:
    """Check venue status/operating slots/blocks; does not reserve or lock a venue."""
    venue = repo.get(venue_id)
    if venue is None:
        raise HTTPException(404, "Venue not found")
    return check_availability(venue, payload, blocks.list_for_venue(venue_id))


@router.get(
    "/{venue_id}/blocks/{block_id}/affected-events", response_model=list[AffectedEvent]
)
def affected_events(
    venue_id: str,
    block_id: str,
    principal: VenueStaffDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
    source: Annotated[EventAllocationSource, Depends(get_event_allocations)],
    today: Annotated[date, Depends(current_venue_date)],
) -> list[AffectedEvent]:
    """Find affected confirmed events; no delivery attempts or database writes."""
    if repo.get(venue_id) is None:
        raise HTTPException(404, "Venue not found")
    block = blocks.get(block_id)
    if block is None or block.venue_id != venue_id:
        raise HTTPException(404, "Venue block not found")
    if block.status != BlockStatus.ACTIVE or block.end_date < today:
        return []
    allocations = source.list_for_period(
        venue_id,
        max(block.start_date, today),
        block.end_date,
    )
    return find_affected_events(block, allocations, today)
