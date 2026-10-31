"""Tentative venue holds (SCRUM-18).

The event's current Event Coordinator holds a venue while the event is being
finalised, then releases the hold or converts it into a pending booking request
for Venue Staff to decide. A hold expires at most 7 days after it is placed; the
coordinator is told 24 hours before and when it expires (see hold_expiry).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.availability_models import Period
from app.booking_models import BookingRequest
from app.booking_notifications import BookingNotifier, get_booking_notifier
from app.booking_repository import BookingEventChangedError, BookingEventNotFoundError
from app.dependencies import Principal, bearer_token, require_event_coordinator
from app.event_requests import EventRequestClient, get_event_client
from app.hold_expiry import run_hold_sweep
from app.hold_models import (
    HOLDABLE_EVENT_STATUSES,
    VenueHold,
    VenueHoldCreate,
    expiry_error,
)
from app.hold_store import (
    HoldEventClosedError,
    HoldForbiddenError,
    HoldNotActiveError,
    HoldNotFoundError,
    VenueHoldStore,
    get_hold_store,
)
from app.routers.venues import RepoDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["venue holds"])

HoldStoreDep = Annotated[VenueHoldStore, Depends(get_hold_store)]
EventClientDep = Annotated[EventRequestClient, Depends(get_event_client)]
CoordinatorDep = Annotated[Principal, Depends(require_event_coordinator)]
TokenDep = Annotated[str, Depends(bearer_token)]
NotifierDep = Annotated[BookingNotifier, Depends(get_booking_notifier)]

NOT_FOUND = "Venue hold not found"
NOT_ACTIVE = "This hold has ended or expired, or its booking request is still pending."
CLOSED = "Holds can only be placed while the event is being finalised."


class HoldConversion(BaseModel):
    hold: VenueHold
    booking: BookingRequest


def _hold_for_coordinator(
    hold_id: str, principal: Principal, token: str, store: VenueHoldStore,
    events: EventRequestClient,
) -> VenueHold:
    """The hold, if the caller is its event's current coordinator; 404 otherwise."""
    hold = store.get(hold_id)
    if hold is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    events.require_coordinator(hold.event_request_id, token, principal.user_id)
    return hold


@router.post(
    "/venues/{venue_id}/holds", response_model=VenueHold, status_code=status.HTTP_201_CREATED
)
def place_hold(
    venue_id: str,
    payload: VenueHoldCreate,
    principal: CoordinatorDep,
    token: TokenDep,
    venues: RepoDep,
    holds: HoldStoreDep,
    events: EventClientDep,
    notifier: NotifierDep,
) -> VenueHold:
    """Hold a venue for an event the caller coordinates. 409 lists what the time
    clashes with, using booking approval's codes plus ``hold_conflict``."""
    if error := expiry_error(payload.expires_at, datetime.now(UTC)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error)
    venue = venues.get(venue_id)
    if venue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    event_request_id = str(payload.event_request_id)
    snapshot = events.snapshot_for_coordinator(event_request_id, token, principal.user_id)
    if snapshot.status not in HOLDABLE_EVENT_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, CLOSED)
    period = Period(
        start_date=payload.start_date, end_date=payload.end_date,
        start_minute=payload.start_minute, end_minute=payload.end_minute,
    )
    try:
        placement = holds.place(venue, event_request_id, period, payload.expires_at, principal.user_id)
    except HoldNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue or event not found") from error
    except HoldForbiddenError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found") from error
    except HoldEventClosedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, CLOSED) from error
    if placement.hold is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            placement.model_dump(mode="json", exclude={"hold"}),
        )
    # A hold placed with less than 24 hours left is due its notice now.
    try:
        run_hold_sweep(holds, notifier)
    except Exception:  # a notice failure never undoes the saved hold
        logger.exception("Hold notice sweep after placing failed")
    return placement.hold


@router.get("/venue-holds", response_model=list[VenueHold])
def list_holds(
    event_request_id: Annotated[UUID, Query()],
    principal: CoordinatorDep,
    token: TokenDep,
    holds: HoldStoreDep,
    events: EventClientDep,
) -> list[VenueHold]:
    """Every hold of an event the caller coordinates, oldest first."""
    events.require_coordinator(str(event_request_id), token, principal.user_id)
    return holds.list_for_event(str(event_request_id))


@router.post("/venue-holds/{hold_id}/release", response_model=VenueHold)
def release_hold(
    hold_id: str,
    principal: CoordinatorDep,
    token: TokenDep,
    holds: HoldStoreDep,
    events: EventClientDep,
) -> VenueHold:
    """Release an active hold, freeing its time straight away."""
    _hold_for_coordinator(hold_id, principal, token, holds, events)
    try:
        return holds.release(hold_id, principal.user_id)
    except HoldNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from error
    except HoldForbiddenError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from error
    except HoldNotActiveError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ACTIVE) from error


@router.post(
    "/venue-holds/{hold_id}/convert",
    response_model=HoldConversion,
    status_code=status.HTTP_201_CREATED,
)
def convert_hold(
    hold_id: str,
    principal: CoordinatorDep,
    token: TokenDep,
    holds: HoldStoreDep,
    events: EventClientDep,
) -> HoldConversion:
    """Turn an active hold into a pending booking request for Venue Staff to
    decide. The hold keeps the time until they decide or it expires."""
    hold = _hold_for_coordinator(hold_id, principal, token, holds, events)
    snapshot = events.snapshot_for_coordinator(hold.event_request_id, token, principal.user_id)
    booking = BookingRequest(
        venue_id=hold.venue_id,
        requested_by=principal.user_id,
        event_request_id=hold.event_request_id,
        event_name=snapshot.event_name,
        expected_attendance=snapshot.expected_attendance,
        requirements_note=snapshot.venue_requirements,
        start_date=hold.start_date,
        end_date=hold.end_date,
        start_minute=hold.start_minute,
        end_minute=hold.end_minute,
    )
    try:
        converted, created = holds.convert(hold_id, booking, snapshot.updated_at)
    except (HoldNotFoundError, HoldForbiddenError, BookingEventNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from error
    except HoldNotActiveError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ACTIVE) from error
    except BookingEventChangedError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Event request changed; refresh before booking",
        ) from error
    return HoldConversion(hold=converted, booking=created)
