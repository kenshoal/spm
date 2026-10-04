"""Venue booking details visible only to Venue Staff."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import Principal, require_venue_staff
from app.models import VenueBookingRequest
from app.routers.venues import RepoDep

router = APIRouter(prefix="/venue-booking-requests", tags=["venue bookings"])
VenueStaffDep = Annotated[Principal, Depends(require_venue_staff)]


@router.get("", response_model=list[VenueBookingRequest])
def list_booking_requests(
    principal: VenueStaffDep,
    repo: RepoDep,
) -> list[VenueBookingRequest]:
    del principal
    # ponytail: this is a role-wide work queue until venue assignment exists.
    return repo.list_booking_requests()
