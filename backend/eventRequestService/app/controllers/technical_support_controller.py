from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from app.config import get_settings
from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
    get_event_request_service,
)
from app.models.technical_support import (
    AssignmentCreate,
    AssignmentResponse,
    CandidateResponse,
    EventTechnicalSupportResponse,
    RequirementCreate,
    RequirementResponse,
)
from app.repositories.coordinator_assignment_repository import (
    SupabaseCoordinatorAssignmentRepository,
)
from app.repositories.technical_support_repository import (
    SupabaseTechnicalSupportRepository,
)
from app.services.notification_client import NotificationClient
from app.services.technical_support_service import TechnicalSupportService

router = APIRouter(prefix="/event-requests", tags=["technical support"])

EVENT_COORDINATOR_ROLE = "event_coordinator"
TECHNICAL_SUPPORT_ROLE = "technical_support"


def get_technical_support_service(request: Request) -> TechnicalSupportService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.technical_support_service
    if service is not None:
        return service

    try:
        repository = SupabaseTechnicalSupportRepository.from_settings(get_settings())
        coordinator_repository = (
            SupabaseCoordinatorAssignmentRepository.from_settings(get_settings())
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured for eventRequestService",
        ) from error

    service = TechnicalSupportService(
        repository,
        get_event_request_service(request),
        coordinator_repository,
        NotificationClient.from_settings(get_settings()),
    )
    request.app.state.technical_support_service = service
    return service


def _require_role(caller: AuthenticatedCaller, role: str) -> None:
    if role not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")


ServiceDependency = Annotated[
    TechnicalSupportService, Depends(get_technical_support_service)
]
CallerDependency = Annotated[AuthenticatedCaller, Depends(get_authenticated_caller)]


@router.post(
    "/{event_request_id}/technical-support/requirements",
    response_model=RequirementResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_requirement(
    event_request_id: UUID,
    payload: RequirementCreate,
    caller: CallerDependency,
    service: ServiceDependency,
) -> RequirementResponse:
    _require_role(caller, EVENT_COORDINATOR_ROLE)
    return service.record_requirement(str(event_request_id), payload, caller.id)


@router.get(
    "/{event_request_id}/technical-support",
    response_model=list[EventTechnicalSupportResponse],
)
def list_technical_support(
    event_request_id: UUID,
    caller: CallerDependency,
    service: ServiceDependency,
) -> list[EventTechnicalSupportResponse]:
    if set(caller.roles).isdisjoint({EVENT_COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return service.list_for_event(str(event_request_id), caller.id, caller.roles)


@router.get(
    "/{event_request_id}/technical-support/requirements/{requirement_id}/candidates",
    response_model=list[CandidateResponse],
)
def list_candidates(
    event_request_id: UUID,
    requirement_id: UUID,
    caller: CallerDependency,
    service: ServiceDependency,
) -> list[CandidateResponse]:
    _require_role(caller, EVENT_COORDINATOR_ROLE)
    return service.list_candidates(
        str(event_request_id), str(requirement_id), caller.id
    )


@router.post(
    "/{event_request_id}/technical-support/requirements/{requirement_id}/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_staff(
    event_request_id: UUID,
    requirement_id: UUID,
    payload: AssignmentCreate,
    caller: CallerDependency,
    service: ServiceDependency,
) -> AssignmentResponse:
    _require_role(caller, EVENT_COORDINATOR_ROLE)
    return service.assign(
        str(event_request_id), str(requirement_id), payload, caller.id
    )
