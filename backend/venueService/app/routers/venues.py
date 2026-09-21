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
from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.models import (
    RoomLayout,
    Slot,
    Venue,
    VenueCreate,
    VenueStatus,
    VenueUpdate,
)
from app.storage import BlockStore, Stores, VenueStore, get_stores

router = APIRouter(prefix="/venues", tags=["venues"])


def get_repository(stores: Annotated[Stores, Depends(get_stores)]) -> VenueStore:
    """Dependency seam so tests can override the store."""

    return stores.venues


RepoDep = Annotated[VenueStore, Depends(get_repository)]
VenueStaffDep = Annotated[Principal, Depends(require_venue_staff)]
AuthenticatedDep = Annotated[Principal, Depends(require_authenticated)]


def get_block_repository(stores: Annotated[Stores, Depends(get_stores)]) -> BlockStore:
    return stores.blocks


BlockRepoDep = Annotated[BlockStore, Depends(get_block_repository)]


@router.get("/{venue_id}/blocks", response_model=list[VenueBlock])
def list_venue_blocks(
    venue_id: str,
    principal: AuthenticatedDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
) -> list[VenueBlock]:
    """List all recorded blocks for a venue, including lifted blocks."""
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
) -> VenueBlock:
    """Validate and store a dated block; booking impact is integrated later."""
    if repo.get(venue_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )
    return blocks.create(venue_id, payload, created_by=principal.user_id)


@router.post("", response_model=Venue, status_code=status.HTTP_201_CREATED)
def create_venue(
    payload: VenueCreate,
    principal: VenueStaffDep,
    repo: RepoDep,
) -> Venue:
    del principal
    return repo.create(payload)


@router.get("", response_model=list[Venue])
def list_venues(principal: AuthenticatedDep, repo: RepoDep) -> list[Venue]:
    del principal
    return repo.list()


@router.get("/search", response_model=list[Venue])
def search_venues(
    principal: AuthenticatedDep,
    repo: RepoDep,
    blocks: BlockRepoDep,
    required_capacity: Annotated[int | None, Query(gt=0)] = None,
    location: Annotated[str | None, Query()] = None,
    slot: Annotated[Slot | None, Query()] = None,
    on_date: Annotated[date | None, Query(alias="date")] = None,
    layout: Annotated[RoomLayout | None, Query()] = None,
    facility: Annotated[list[str] | None, Query()] = None,
    accessibility: Annotated[list[str] | None, Query()] = None,
) -> list[Venue]:
    """Return venues matching every supplied filter.

    With a date and slot, exclude venues blocked for that period. With only a
    date, require at least one operating slot unaffected by active blocks.
    Without a date, no dated availability claim is made. Reservations are not
    yet checked.
    """

    del principal

    wanted_facilities = {f.lower() for f in facility} if facility else set()
    wanted_accessibility = {a.lower() for a in accessibility} if accessibility else set()

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
                venue, on_date, blocks.list_for_venue(venue.id)
            )
            if not remaining_slots or (slot is not None and slot not in remaining_slots):
                continue
        results.append(venue)
    return results


@router.get("/{venue_id}", response_model=Venue)
def get_venue(venue_id: str, principal: AuthenticatedDep, repo: RepoDep) -> Venue:
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
