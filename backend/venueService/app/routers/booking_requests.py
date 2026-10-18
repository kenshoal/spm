"""Venue booking requests (SCRUM-32).

An Event Coordinator asks for a venue, a date range and slots for an event they
are currently assigned to. Submitting creates a pending request and reserves
nothing; deciding it belongs to a later story.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.booking_models import (
    BookingRequest,
    BookingRequestCreate,
    BookingRequestStatus,
)
from app.booking_repository import (
    BookingNotCancellableError,
    BookingRequestNotFoundError,
    BookingRequestStore,
    get_booking_repository,
)
from app.dependencies import (
    Principal,
    bearer_token,
    require_booking_reader,
    require_event_booking_reader,
    require_event_coordinator,
    require_venue_staff,
)
from app.event_requests import EventRequestClient, get_event_client
from app.routers.venues import RepoDep

router = APIRouter(prefix="/booking-requests", tags=["booking requests"])

BookingRepoDep = Annotated[BookingRequestStore, Depends(get_booking_repository)]
EventClientDep = Annotated[EventRequestClient, Depends(get_event_client)]
CoordinatorDep = Annotated[Principal, Depends(require_event_coordinator)]
TokenDep = Annotated[str, Depends(bearer_token)]
VenueStaffDep = Annotated[Principal, Depends(require_venue_staff)]
ReaderDep = Annotated[Principal, Depends(require_booking_reader)]
EventReaderDep = Annotated[Principal, Depends(require_event_booking_reader)]


@router.post("", response_model=BookingRequest, status_code=status.HTTP_201_CREATED)
def submit_booking_request(
    payload: BookingRequestCreate,
    principal: CoordinatorDep,
    token: TokenDep,
    venues: RepoDep,
    bookings: BookingRepoDep,
    events: EventClientDep,
) -> BookingRequest:
    venue = venues.get(payload.venue_id)
    if venue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")

    event_request_id = str(payload.event_request_id)
    snapshot = events.snapshot_for_coordinator(
        event_request_id, token, principal.user_id
    )
    return bookings.create(
        BookingRequest(
            venue_id=venue.id,
            requested_by=principal.user_id,
            event_request_id=event_request_id,
            event_name=snapshot.event_name,
            expected_attendance=snapshot.expected_attendance,
            requirements_note=snapshot.venue_requirements,
            start_date=payload.start_date,
            end_date=payload.end_date,
            slots=payload.slots,
        )
    )


@router.get("", response_model=list[BookingRequest])
def list_booking_requests(
    principal: VenueStaffDep,
    bookings: BookingRepoDep,
    status_filter: Annotated[
        BookingRequestStatus, Query(alias="status")
    ] = BookingRequestStatus.PENDING,
) -> list[BookingRequest]:
    """The Venue Staff queue: requests with one status, oldest first."""

    del principal
    return bookings.list_by_status(status_filter)


# Declared before "/{booking_id}" so "mine" is not read as an id.
@router.get("/mine", response_model=list[BookingRequest])
def list_my_booking_requests(
    principal: CoordinatorDep, bookings: BookingRepoDep
) -> list[BookingRequest]:
    """The caller's own requests, newest first."""

    return bookings.list_for_requester(principal.user_id)


# Declared before "/{booking_id}"; the two-segment path cannot clash with it.
@router.get("/event/{event_request_id}", response_model=list[BookingRequest])
def list_event_booking_requests(
    event_request_id: UUID,
    principal: EventReaderDep,
    token: TokenDep,
    bookings: BookingRepoDep,
    events: EventClientDep,
) -> list[BookingRequest]:
    """Every venue booking of one event, oldest first, with its status.

    Venue Staff and the Safety Officer read any event. A Coordinator reads only
    the events they are currently assigned to, checked with eventRequestService
    on every call.
    """

    event_id = str(event_request_id)
    if not {"venue_staff", "safety_officer"} & set(principal.roles):
        events.require_coordinator(event_id, token, principal.user_id)
    return bookings.list_for_event(event_id)


@router.get("/{booking_id}", response_model=BookingRequest)
def get_booking_request(
    booking_id: str, principal: ReaderDep, bookings: BookingRepoDep
) -> BookingRequest:
    booking = bookings.get(booking_id)
    # A Coordinator sees only their own; anyone else's looks like an unknown id.
    if booking is None or (
        "venue_staff" not in principal.roles
        and booking.requested_by != principal.user_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking request not found")
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingRequest)
def cancel_booking_request(
    booking_id: str,
    principal: CoordinatorDep,
    token: TokenDep,
    bookings: BookingRepoDep,
    events: EventClientDep,
) -> BookingRequest:
    """Cancel one pending or approved booking; the event's other bookings stay.

    Only the event's current Coordinator can cancel, checked again here, so a
    reassignment moves the right with the event, not with the requester.
    """

    booking = bookings.get(booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking request not found")
    events.require_coordinator(booking.event_request_id, token, principal.user_id)
    try:
        return bookings.cancel(booking_id, principal.user_id)
    except BookingRequestNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Booking request not found"
        ) from None
    except BookingNotCancellableError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Booking request cannot be cancelled"
        ) from None
