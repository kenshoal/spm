"""Venue catalogue CRUD and venue search / filtering.

Covers two backlog cards:

* "Maintain the Venue Catalogue" — Venue Staff create and update venue records;
  authorised users view them.
* "Search and Filter Venues" — Event Coordinators filter venues by event
  requirements; results match all applied filters, exclude venues below the
  required capacity, and exclude venues that are not available.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic_core import PydanticCustomError

from app.availability import is_free
from app.block_models import VenueBlock, VenueBlockCreate
from app.booking_models import BookingRequestStatus
from app.booking_notifications import (
    BookingNotifier,
    block_affects_booking_event,
    current_venue_date,
    get_booking_notifier,
)
from app.booking_repository import BookingRequestStore, get_booking_repository
from app.dependencies import (
    Principal,
    require_block_reader,
    require_venue_location_reader,
    require_venue_staff,
    require_venue_viewer,
)
from app.models import (
    RoomLayout,
    Venue,
    VenueCreate,
    VenueLocation,
    VenueStatus,
    VenueUpdate,
)
from app.repository import VenueStore, get_repository
from app.slots import check_time_range, times_overlap
from app.storage import BlockStore, get_block_repository

router = APIRouter(prefix="/venues", tags=["venues"])


RepoDep = Annotated[VenueStore, Depends(get_repository)]
VenueStaffDep = Annotated[Principal, Depends(require_venue_staff)]
VenueViewerDep = Annotated[Principal, Depends(require_venue_viewer)]
VenueLocationReaderDep = Annotated[Principal, Depends(require_venue_location_reader)]
BlockRepoDep = Annotated[BlockStore, Depends(get_block_repository)]
BookingRepoDep = Annotated[BookingRequestStore, Depends(get_booking_repository)]


@router.get("/{venue_id}/blocks", response_model=list[VenueBlock])
def list_venue_blocks(
    venue_id: str,
    principal: Annotated[Principal, Depends(require_block_reader)],
    repo: RepoDep,
    blocks: BlockRepoDep,
) -> list[VenueBlock]:
    """List all recorded blocks for a venue, including lifted blocks.

    Venue Staff and the Safety Officer only: reasons are internal planning
    information (SCRUM-60 AC2).
    """
    del principal
    if repo.get(venue_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )
    return blocks.list_for_venue(venue_id)


@router.post(
    "/{venue_id}/blocks",
    response_model=VenueBlock,
    status_code=status.HTTP_201_CREATED,
)
def create_venue_block(
    venue_id: str,
    payload: VenueBlockCreate,
    principal: VenueStaffDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
    bookings: BookingRepoDep,
    notifier: Annotated[BookingNotifier, Depends(get_booking_notifier)],
    today: Annotated[date, Depends(current_venue_date)],
) -> VenueBlock:
    """Store a dated block, then alert the Coordinators of affected bookings.

    An approved booking that shares a date with the block, overlaps it in time
    and has not ended is affected (SCRUM-23 AC3, SCRUM-65). The block is saved regardless; notifying
    never fails or undoes it.
    """
    venue = repo.get(venue_id)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )
    block = blocks.create(venue_id, payload, created_by=principal.user_id)
    for booking in bookings.list_by_status(BookingRequestStatus.APPROVED):
        if (
            booking.venue_id == venue_id
            and booking.end_date >= today
            and times_overlap(
                block.start_date,
                block.end_date,
                block.start_minute,
                block.end_minute,
                booking.start_date,
                booking.end_date,
                booking.start_minute,
                booking.end_minute,
            )
        ):
            notifier.send(block_affects_booking_event(block, booking, venue.name))
            bookings.mark_needs_new_venue(booking.id)
    return block


@router.post("", response_model=Venue, status_code=status.HTTP_201_CREATED)
def create_venue(
    payload: VenueCreate,
    principal: VenueStaffDep,
    repo: RepoDep,
) -> Venue:
    del principal
    return repo.create(payload)


@router.get("", response_model=list[Venue])
def list_venues(principal: VenueViewerDep, repo: RepoDep) -> list[Venue]:
    del principal
    return repo.list()


# Declared before GET /{venue_id}: FastAPI matches routes in declaration order,
# so declaring it later would treat "locations" as a venue id.
@router.get("/locations", response_model=list[VenueLocation])
def list_venue_locations(
    principal: VenueLocationReaderDep, repo: RepoDep
) -> list[VenueLocation]:
    """Every venue's id, name and building, blocked venues included: a blocked
    room still locates the equipment stored in it (SCRUM-13 D11)."""
    del principal
    return [
        VenueLocation(id=v.id, name=v.name, location=v.location) for v in repo.list()
    ]


@router.get("/search", response_model=list[Venue])
def search_venues(
    principal: VenueViewerDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
    bookings: BookingRepoDep,
    required_capacity: Annotated[int | None, Query(gt=0)] = None,
    location: Annotated[str | None, Query()] = None,
    on_date: Annotated[date | None, Query(alias="date")] = None,
    start_minute: Annotated[int | None, Query()] = None,
    end_minute: Annotated[int | None, Query()] = None,
    layout: Annotated[RoomLayout | None, Query()] = None,
    facility: Annotated[list[str] | None, Query()] = None,
    accessibility: Annotated[list[str] | None, Query()] = None,
) -> list[Venue]:
    """Return venues matching every supplied filter.

    With a date and a start and end time (minutes after midnight, SCRUM-65),
    exclude venues blocked or booked at an overlapping time. With only a date,
    require some free time within 07:00-24:00 that day. Without a date, no
    dated availability claim is made, so times need a date.
    """

    del principal
    _check_search_times(on_date, start_minute, end_minute)

    wanted_facilities = {f.lower() for f in facility} if facility else set()
    wanted_accessibility = {a.lower() for a in accessibility} if accessibility else set()

    approved = (
        bookings.list_by_status(BookingRequestStatus.APPROVED)
        if on_date is not None
        else []
    )
    results: list[Venue] = []
    for venue in repo.list():
        if venue.status is not VenueStatus.AVAILABLE:
            continue
        if required_capacity is not None and venue.max_capacity < required_capacity:
            continue
        if location is not None and location.lower() not in venue.location.lower():
            continue
        if layout is not None and layout not in venue.supported_layouts:
            continue
        if wanted_facilities and not wanted_facilities.issubset(
            {f.lower() for f in venue.facilities}
        ):
            continue
        if wanted_accessibility and not wanted_accessibility.issubset(
            {a.lower() for a in venue.accessibility_features}
        ):
            continue
        if on_date is not None and not is_free(
            venue, on_date, start_minute, end_minute,
            blocks.list_for_venue(venue.id), approved,
        ):
            continue
        results.append(venue)
    return results


def _check_search_times(
    on_date: date | None, start_minute: int | None, end_minute: int | None
) -> None:
    """422 with the same reason codes as a booking (SCRUM-65)."""
    if start_minute is None and end_minute is None:
        return
    try:
        if start_minute is None or end_minute is None:
            raise PydanticCustomError(
                "times_incomplete", "Give both a start and an end time."
            )
        if on_date is None:
            raise PydanticCustomError("date_required", "Times need a date.")
        check_time_range(start_minute, end_minute)
    except PydanticCustomError as error:
        raise HTTPException(
            422,
            [{"type": error.type, "loc": ["query"], "msg": error.message()}],
        ) from None


@router.get("/{venue_id}", response_model=Venue)
def get_venue(venue_id: str, principal: VenueViewerDep, repo: RepoDep) -> Venue:
    del principal
    venue = repo.get(venue_id)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )
    return venue


@router.patch("/{venue_id}", response_model=Venue)
def update_venue(
    venue_id: str,
    payload: VenueUpdate,
    principal: VenueStaffDep,
    repo: RepoDep,
) -> Venue:
    # SCRUM-20 AC6: setup and turnaround go through update_timing, which flags the
    # bookings a change affects; the other fields are a plain update.
    timing = payload.model_dump(
        include={"setup_minutes", "turnaround_minutes"}, exclude_unset=True
    )
    rest = VenueUpdate(
        **payload.model_dump(exclude={"setup_minutes", "turnaround_minutes"}, exclude_unset=True)
    )
    if timing:
        venue = repo.update_timing(
            venue_id,
            timing.get("setup_minutes"),
            timing.get("turnaround_minutes"),
            principal.user_id,
        )
        if venue is not None and rest.model_fields_set:
            venue = repo.update(venue_id, rest)
    else:
        venue = repo.update(venue_id, payload)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )
    return venue
