from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.config import get_settings
from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
    get_event_request_service,
)
from app.models.coordinator_assignment import (
    CoordinatorAssignmentResponse,
    CoordinatorAssignRequest,
    CurrentAssignmentResponse,
)
from app.models.event_request import EventRequestResponse
from app.repositories.coordinator_assignment_repository import (
    SupabaseCoordinatorAssignmentRepository,
)
from app.services.coordinator_assignment_service import CoordinatorAssignmentService
from app.services.event_request_service import EventRequestNotFoundError
from app.services.notification_client import NotificationClient

router = APIRouter(prefix="/event-requests", tags=["coordinator assignment"])


def get_coordinator_assignment_service(
    request: Request,
) -> CoordinatorAssignmentService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.coordinator_assignment_service
    if service is not None:
        return service

    try:
        repository = SupabaseCoordinatorAssignmentRepository.from_settings(
            get_settings()
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured for eventRequestService",
        ) from error

    service = CoordinatorAssignmentService(
        repository,
        get_event_request_service(request),
        NotificationClient.from_settings(get_settings()),
    )
    request.app.state.coordinator_assignment_service = service
    return service


def get_operations_manager_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    caller = get_authenticated_caller(authorization)
    if "event_operations_manager" not in caller.roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only an Event Coordinator Lead can assign a Coordinator",
        )
    return caller.id


ServiceDependency = Annotated[
    CoordinatorAssignmentService, Depends(get_coordinator_assignment_service)
]
CallerDependency = Annotated[AuthenticatedCaller, Depends(get_authenticated_caller)]
OperationsManagerDependency = Annotated[str, Depends(get_operations_manager_id)]


@router.get(
    "/awaiting-assignment",
    response_model=list[EventRequestResponse],
)
def list_awaiting_assignment(
    _assigned_by: OperationsManagerDependency,
    service: ServiceDependency,
) -> list[EventRequestResponse]:
    return service.list_awaiting_assignment()


@router.get(
    "/assignments",
    response_model=list[CurrentAssignmentResponse],
)
def list_current_assignments(
    _assigned_by: OperationsManagerDependency,
    service: ServiceDependency,
) -> list[CurrentAssignmentResponse]:
    return service.list_current_assignments()


@router.post(
    "/{event_request_id}/coordinator",
    response_model=CoordinatorAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_coordinator(
    event_request_id: str,
    payload: CoordinatorAssignRequest,
    assigned_by: OperationsManagerDependency,
    service: ServiceDependency,
) -> CoordinatorAssignmentResponse:
    return service.assign(event_request_id, payload, assigned_by)


@router.get(
    "/{event_request_id}/coordinator",
    response_model=CoordinatorAssignmentResponse,
)
def get_coordinator(
    event_request_id: str,
    caller: CallerDependency,
    service: ServiceDependency,
) -> CoordinatorAssignmentResponse:
    roles = set(caller.roles)
    if "event_operations_manager" in roles:
        return service.get_current(event_request_id)

    if "event_organiser" in roles:
        try:
            # Owner or same-organisation colleague (SCRUM-39).
            service.event_request_service.get_viewable(event_request_id, caller.id)
            return service.get_current(event_request_id)
        except EventRequestNotFoundError:
            pass  # The caller's coordinator role may still grant access.

    assignment = service.get_current(event_request_id)
    if (
        "event_coordinator" in roles
        and assignment.coordinator_id == caller.id
    ):
        return assignment

    if roles.isdisjoint({"event_organiser", "event_coordinator"}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")
