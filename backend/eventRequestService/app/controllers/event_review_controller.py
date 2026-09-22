from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.controllers.coordinator_assignment_controller import (
    get_coordinator_assignment_service,
)
from app.controllers.event_request_controller import (
    get_coordinator_id,
    get_event_request_service,
)
from app.models.event_request import EventRequestResponse
from app.services.event_review_service import EventReviewService

router = APIRouter(prefix="/event-requests", tags=["event review"])


def get_event_review_service(request: Request) -> EventReviewService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.event_review_service
    if service is not None:
        return service

    service = EventReviewService(
        get_event_request_service(request),
        get_coordinator_assignment_service(request),
    )
    request.app.state.event_review_service = service
    return service


ServiceDependency = Annotated[EventReviewService, Depends(get_event_review_service)]
CallerDependency = Annotated[str, Depends(get_coordinator_id)]


@router.post("/{event_request_id}/review", response_model=EventRequestResponse)
def start_review(
    event_request_id: str,
    caller_id: CallerDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.start_review(event_request_id, caller_id)
