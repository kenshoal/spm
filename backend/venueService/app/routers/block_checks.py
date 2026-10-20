"""Read-only availability check for booking callers."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.availability_models import AvailabilityResult, Period
from app.block_checks import check_availability
from app.booking_models import BookingRequestStatus
from app.booking_repository import BookingRequestStore, get_booking_repository
from app.dependencies import Principal, require_booking_reader
from app.routers.venues import BlockRepoDep, RepoDep

router = APIRouter(prefix="/venues", tags=["venue block checks"])


@router.post("/{venue_id}/availability", response_model=AvailabilityResult)
def availability(
    venue_id: str,
    payload: Period,
    principal: Annotated[Principal, Depends(require_booking_reader)],
    repo: RepoDep,
    blocks: BlockRepoDep,
    bookings: Annotated[BookingRequestStore, Depends(get_booking_repository)],
) -> AvailabilityResult:
    """Check venue status, blocks and approved bookings by date and time; does
    not reserve or lock a venue.

    Venue Staff and Event Coordinators only. The result carries dates, times and
    reason codes, never the blocks' free-text reasons.
    """
    venue = repo.get(venue_id)
    if venue is None:
        raise HTTPException(404, "Venue not found")
    return check_availability(
        venue,
        payload,
        blocks.list_for_venue(venue_id),
        bookings.list_by_status(BookingRequestStatus.APPROVED),
    )
