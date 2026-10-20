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
from app.routers.venues import BlockRepoDep, BookingRepoDep, RepoDep, VenueViewerDep

router = APIRouter(prefix="/venues", tags=["venue calendar"])

# YYYY-MM, with a real year (0000 is not a calendar year; the regex engine has
# no look-ahead, so the years are listed as alternatives).
MONTH_PATTERN = r"^(000[1-9]|00[1-9]\d|0[1-9]\d{2}|[1-9]\d{3})-(0[1-9]|1[0-2])$"


@router.get("/{venue_id}/calendar", response_model=VenueCalendar)
def venue_calendar(
    venue_id: str,
    month: Annotated[str, Query(pattern=MONTH_PATTERN)],
    principal: VenueViewerDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
    bookings: BookingRepoDep,
) -> VenueCalendar:
    del principal
    venue = repo.get(venue_id)
    if venue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    first, last = month_bounds(month)
    return build_calendar(
        venue,
        month,
        blocks.list_for_venue(venue.id),
        bookings.list_approved_for_venue(venue.id, first, last),
    )
