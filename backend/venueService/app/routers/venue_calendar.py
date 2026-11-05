"""Venue availability calendar (SCRUM-31).

Coordinators, Venue Staff and Safety Officers (the roles that can already view
the venue catalogue) read one month of slot states for a venue. The response
never carries block reasons, event names or ids; those stay on the Venue Staff
page.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.calendar_view import VenueCalendar, build_calendar, month_bounds
from app.routers.venues import (
    BlockRepoDep,
    BookingRepoDep,
    HoldStoreDep,
    RepoDep,
    VenueViewerDep,
)

router = APIRouter(prefix="/venues", tags=["venue calendar"])

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("/{venue_id}/calendar", response_model=VenueCalendar)
def venue_calendar(
    venue_id: str,
    month: Annotated[str, Query(pattern=MONTH_PATTERN)],
    principal: VenueViewerDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
    bookings: BookingRepoDep,
    holds: HoldStoreDep,
) -> VenueCalendar:
    del principal
    try:
        first, last = month_bounds(month)
    except ValueError:
        # The pattern allows 0000, which is not a calendar year.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid month"
        ) from None
    venue = repo.get(venue_id)
    if venue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    return build_calendar(
        venue,
        month,
        blocks.list_for_venue(venue.id),
        bookings.list_approved_for_venue(venue.id, first, last),
        holds.list_for_venue(venue.id, first, last),
    )
