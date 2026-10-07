"""Venue Staff decide on venue booking requests (SCRUM-15).

Approving a pending request makes it the confirmed booking. Approval is
refused with 409 when the venue is unavailable, a slot is not operated, an
active block overlaps or another approved request overlaps; each refusal is
recorded and readable by Venue Staff. A saved decision notifies the requesting
Coordinator.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.booking_decision_store import (
    BookingAlreadyDecidedError,
    BookingDecisionStore,
    BookingNotFoundError,
    BookingRefusal,
    get_booking_decision_store,
)
from app.booking_decisions import DecisionDetails
from app.booking_models import BookingRequest
from app.booking_notifications import BookingNotifier, get_booking_notifier
from app.booking_repository import BookingRequestStore, get_booking_repository
from app.dependencies import Principal, require_venue_staff
from app.routers.venues import RepoDep

router = APIRouter(prefix="/booking-requests", tags=["booking decisions"])

DecisionStoreDep = Annotated[BookingDecisionStore, Depends(get_booking_decision_store)]
BookingRepoDep = Annotated[BookingRequestStore, Depends(get_booking_repository)]
VenueStaffDep = Annotated[Principal, Depends(require_venue_staff)]
NotifierDep = Annotated[BookingNotifier, Depends(get_booking_notifier)]


@router.post("/{booking_id}/decision", response_model=BookingRequest)
def decide_booking_request(
    booking_id: str,
    payload: DecisionDetails,
    principal: VenueStaffDep,
    store: DecisionStoreDep,
    venues: RepoDep,
    notifier: NotifierDep,
) -> BookingRequest:
    """Approve or reject a pending request; the decider comes from the token.

    Only a saved decision notifies the requesting Coordinator (AC4).
    """
    try:
        outcome = store.decide(booking_id, payload, decided_by=principal.user_id)
    except BookingNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Booking request not found"
        ) from None
    except BookingAlreadyDecidedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Booking request has already been decided"
        ) from None
    if outcome.refused:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "Approval refused",
                "refusal_codes": outcome.refusal_codes,
                "conflicting_block_ids": outcome.conflicting_block_ids,
                "conflicting_booking_ids": outcome.conflicting_booking_ids,
            },
        )
    venue = venues.get(outcome.booking.venue_id)
    notifier.notify_decision(outcome.booking, venue.name if venue else None)
    return outcome.booking


@router.get("/{booking_id}/refusals", response_model=list[BookingRefusal])
def list_booking_refusals(
    booking_id: str,
    principal: VenueStaffDep,
    bookings: BookingRepoDep,
    store: DecisionStoreDep,
) -> list[BookingRefusal]:
    """Every refused approval for a request, oldest first. Venue Staff only."""
    del principal
    if bookings.get(booking_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking request not found")
    return store.list_refusals(booking_id)
