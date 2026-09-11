"""Venue catalogue CRUD.

Covers "Maintain the Venue Catalogue" — Venue Staff create and update venue
records; authorised users view them.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.models import Venue, VenueCreate, VenueUpdate
from app.repository import VenueRepository, repository

router = APIRouter(prefix="/venues", tags=["venues"])


def get_repository() -> VenueRepository:
    """Dependency seam so tests can override the store."""

    return repository


RepoDep = Annotated[VenueRepository, Depends(get_repository)]
VenueStaffDep = Annotated[Principal, Depends(require_venue_staff)]
AuthenticatedDep = Annotated[Principal, Depends(require_authenticated)]


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
