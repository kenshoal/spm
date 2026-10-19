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

from app.availability import available_slots
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
    Slot,
    Venue,
    VenueCreate,
    VenueLocation,
    VenueStatus,
    VenueUpdate,
)
from app.repository import VenueStore, get_repository
from app.slots import overlaps
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

    An approved booking that shares a date and slot with the block and has not
    ended is affected (SCRUM-23 AC3). The block is saved regardless; notifying
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
            and overlaps(
                block.start_date,
                block.end_date,
                block.slots,
                booking.start_date,
                booking.end_date,
                booking.slots,
            )
        ):
            notifier.send(block_affects_booking_event(block, booking, venue.name))
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
    slot: Annotated[Slot | None, Query()] = None,
    on_date: Annotated[date | None, Query(alias="date")] = None,
    layout: Annotated[RoomLayout | None, Query()] = None,
    facility: Annotated[list[str] | None, Query()] = None,
    accessibility: Annotated[list[str] | None, Query()] = None,
) -> list[Venue]:
    """Return venues matching every supplied filter.

    With a date and slot, exclude venues blocked or booked for that period.
    With only a date, require at least one operating slot free of active blocks
    and approved bookings. Without a date, no dated availability claim is made.
    """

    del principal

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
        if slot is not None and slot not in venue.operating_slots:
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
        if on_date is not None:
            remaining_slots = available_slots(
                venue, on_date, blocks.list_for_venue(venue.id), approved
            )
            if not remaining_slots or (slot is not None and slot not in remaining_slots):
                continue
        results.append(venue)
    return results


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
    del principal
    venue = repo.update(venue_id, payload)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )
    return venue
