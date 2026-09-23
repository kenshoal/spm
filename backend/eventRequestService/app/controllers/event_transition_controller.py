from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.controllers.event_request_controller import (
    get_coordinator_id,
    get_event_request_service,
)
from app.models.event_request import EventRequestResponse
from app.services.event_transition_service import EventTransitionService

router = APIRouter(prefix="/event-requests", tags=["event transitions"])


def get_event_transition_service(request: Request) -> EventTransitionService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.event_transition_service
    if service is not None:
        return service

    service = EventTransitionService(get_event_request_service(request))
    request.app.state.event_transition_service = service
    return service


ServiceDependency = Annotated[
    EventTransitionService, Depends(get_event_transition_service)
]
CallerDependency = Annotated[str, Depends(get_coordinator_id)]


@router.post("/{event_request_id}/review", response_model=EventRequestResponse)
def start_review(
    event_request_id: str,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.start_review(event_request_id, caller_id)


@router.post(
    "/{event_request_id}/cancellation", response_model=EventRequestResponse
)
def cancel_event(
    event_request_id: str,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.cancel(event_request_id, caller_id)


@router.post(
    "/{event_request_id}/completion", response_model=EventRequestResponse
)
def complete_event(
    event_request_id: str,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.complete(event_request_id, caller_id)
