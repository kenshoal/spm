from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import get_settings
from app.controllers.event_request_controller import (
    EVENT_COORDINATOR_ROLE,
    AuthenticatedCaller,
    get_authenticated_caller,
    get_coordinator_id,
    get_event_request_service,
)
from app.models.event_request import (
    EventRequestResponse,
    EventRequestStatus,
    EventReviewDecision,
    SafetyDecision,
    SafetyReviewResponse,
)
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)
from app.services.event_transition_service import EventTransitionService
from app.services.notification_client import NotificationClient

router = APIRouter(prefix="/event-requests", tags=["event transitions"])


def get_event_transition_service(request: Request) -> EventTransitionService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.event_transition_service
    if service is not None:
        return service

    # Evaluated left to right: an unconfigured Supabase is reported as a 503 by
    # get_event_request_service before the settings are read again.
    service = EventTransitionService(
        get_event_request_service(request),
        NotificationClient.from_settings(get_settings()),
    )
    request.app.state.event_transition_service = service
    return service


ServiceDependency = Annotated[
    EventTransitionService, Depends(get_event_transition_service)
]
CallerDependency = Annotated[str, Depends(get_coordinator_id)]
AuthenticatedDependency = Annotated[
    AuthenticatedCaller, Depends(get_authenticated_caller)
]
SAFETY_OFFICER_ROLE = "safety_officer"


@router.post("/{event_request_id}/review", response_model=EventRequestResponse)
def start_review(
    event_request_id: UUID,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.start_review(str(event_request_id), caller_id)


@router.post(
    "/{event_request_id}/resume-review", response_model=EventRequestResponse
)
def resume_review(
    event_request_id: UUID,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.resume_review(str(event_request_id), caller_id)


@router.post("/{event_request_id}/decision", response_model=EventRequestResponse)
def decide_review(
    event_request_id: UUID,
    payload: EventReviewDecision,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.decide(str(event_request_id), caller_id, payload)


@router.post("/{event_request_id}/planning", response_model=EventRequestResponse)
def start_planning(
    event_request_id: UUID,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.start_planning(str(event_request_id), caller_id)


@router.post(
    "/{event_request_id}/cancellation", response_model=EventRequestResponse
)
def cancel_event(
    event_request_id: UUID,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.cancel(str(event_request_id), caller_id)


@router.post(
    "/{event_request_id}/completion", response_model=EventRequestResponse
)
def complete_event(
    event_request_id: UUID,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.complete(str(event_request_id), caller_id)


@router.get("/safety-queue", response_model=list[EventRequestResponse])
def safety_queue(
    caller: AuthenticatedDependency,
    event_requests: Annotated[EventRequestService, Depends(get_event_request_service)],
) -> list[EventRequestResponse]:
    """SCRUM-60 AC2: events waiting for a safety check, longest-waiting first.
    The status change bumps updated_at, so it stands for "entered Safety Review".
    Venue and equipment details come from their own services."""
    if SAFETY_OFFICER_ROLE not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    waiting = event_requests.list_by_status(EventRequestStatus.SAFETY_REVIEW)
    return sorted(waiting, key=lambda request: request.updated_at)


@router.post(
    "/{event_request_id}/safety-decision", response_model=EventRequestResponse
)
def decide_safety(
    event_request_id: UUID,
    payload: SafetyDecision,
    caller: AuthenticatedDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    """SCRUM-60: the Safety Officer approves or asks for changes. The database
    re-checks the role, so a token that outlived it is still refused."""
    if SAFETY_OFFICER_ROLE not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return service.decide_safety(str(event_request_id), caller.id, payload)


@router.get(
    "/{event_request_id}/safety-reviews",
    response_model=list[SafetyReviewResponse],
)
def list_safety_reviews(
    event_request_id: UUID,
    caller: AuthenticatedDependency,
    event_requests: Annotated[EventRequestService, Depends(get_event_request_service)],
) -> list[SafetyReviewResponse]:
    """Safety Officers and the event's assigned Coordinator read the decisions.
    An unassigned Coordinator gets 404, as for the event itself (SCRUM-39)."""
    request_id = str(event_request_id)
    if SAFETY_OFFICER_ROLE not in caller.roles:
        if EVENT_COORDINATOR_ROLE not in caller.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        if event_requests.latest_coordinator_id(request_id) != caller.id:
            raise EventRequestNotFoundError(request_id)
    event_requests.get_by_id(request_id)
    return event_requests.list_safety_reviews(request_id)
