from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.controllers.event_request_controller import (
    get_coordinator_id,
    get_event_request_service,
)
from app.models.event_request import EventRequestResponse, EventReviewDecision
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
