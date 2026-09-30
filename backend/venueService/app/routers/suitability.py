"""Venue suitability check.

Covers the backlog card "Check Venue Suitability" — Event Coordinators see
whether a venue appears to meet an event's requirements before proposing it.
The check is advisory only: it never books or holds the venue.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.routers.venues import AuthenticatedDep, RepoDep
from app.suitability import check_suitability
from app.suitability_models import SuitabilityRequest, SuitabilityResult

router = APIRouter(prefix="/venues", tags=["venue suitability"])


@router.post("/{venue_id}/suitability", response_model=SuitabilityResult)
def check_venue_suitability(
    venue_id: str,
    payload: SuitabilityRequest,
    principal: AuthenticatedDep,
    repo: RepoDep,
) -> SuitabilityResult:
    del principal
    venue = repo.get(venue_id)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )
    return check_suitability(venue, payload)
