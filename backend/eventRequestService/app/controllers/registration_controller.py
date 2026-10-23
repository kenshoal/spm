from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from app.clock import get_now
from app.config import get_settings
from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
)
from app.models.registration import (
    CheckInResponse,
    ManualRegistrationCreate,
    ManualRegistrationResponse,
    PublicEventResponse,
    RegistrationInfoResponse,
    RegistrationResponse,
)
from app.repositories.coordinator_assignment_repository import (
    SupabaseCoordinatorAssignmentRepository,
)
from app.repositories.registration_repository import SupabaseRegistrationRepository
from app.services.registration_service import (
    EVENT_COORDINATOR_ROLE,
    EVENT_ORGANISER_ROLE,
    RegistrationService,
)

router = APIRouter(prefix="/attendee", tags=["attendee registration"])
management_router = APIRouter(prefix="/event-requests", tags=["registration info"])
ATTENDEE_ROLE = "attendee"


def get_registration_service(request: Request) -> RegistrationService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.registration_service
    if service is not None:
        return service

    try:
        repository = SupabaseRegistrationRepository.from_settings(get_settings())
        coordinators = SupabaseCoordinatorAssignmentRepository.from_settings(
            get_settings()
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured for eventRequestService",
        ) from error

    service = RegistrationService(repository, coordinators)
    request.app.state.registration_service = service
    return service


def get_attendee_id(
    caller: Annotated[AuthenticatedCaller, Depends(get_authenticated_caller)],
) -> str:
    if ATTENDEE_ROLE not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return caller.id


ServiceDependency = Annotated[RegistrationService, Depends(get_registration_service)]
AttendeeDependency = Annotated[str, Depends(get_attendee_id)]
NowDependency = Annotated[datetime, Depends(get_now)]


@router.get("/events", response_model=list[PublicEventResponse])
def list_open_events(
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
    now: NowDependency,
) -> list[dict]:
    return service.list_open_events(now)


@router.get("/events/{event_id}", response_model=PublicEventResponse)
def get_event(
    event_id: UUID,
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
) -> dict:
    return service.get_event(str(event_id))


@router.post(
    "/events/{event_id}/registrations",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_for_event(
    event_id: UUID,
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
    now: NowDependency,
) -> dict:
    return service.register(str(event_id), attendee_id, now)


@router.get("/registrations", response_model=list[RegistrationResponse])
def list_my_registrations(
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
) -> list[dict]:
    return service.list_registrations(attendee_id)


@management_router.get(
    "/{event_request_id}/registrations", response_model=RegistrationInfoResponse
)
def get_registration_info(
    event_request_id: UUID,
    caller: Annotated[AuthenticatedCaller, Depends(get_authenticated_caller)],
    service: ServiceDependency,
) -> dict:
    if set(caller.roles).isdisjoint({EVENT_ORGANISER_ROLE, EVENT_COORDINATOR_ROLE}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return service.registration_info(str(event_request_id), caller.id, caller.roles)


@management_router.post(
    "/{event_request_id}/registrations",
    response_model=ManualRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_attendee(
    event_request_id: UUID,
    payload: ManualRegistrationCreate,
    caller: Annotated[AuthenticatedCaller, Depends(get_authenticated_caller)],
    service: ServiceDependency,
) -> dict:
    if EVENT_COORDINATOR_ROLE not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return service.register_attendee(
        str(event_request_id), caller.id, payload.attendee_email
    )


@management_router.post(
    "/{event_request_id}/registrations/{registration_id}/check-in",
    response_model=CheckInResponse,
)
def check_in_attendee(
    event_request_id: UUID,
    registration_id: UUID,
    caller: Annotated[AuthenticatedCaller, Depends(get_authenticated_caller)],
    service: ServiceDependency,
    now: NowDependency,
) -> dict:
    if EVENT_COORDINATOR_ROLE not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return service.check_in(
        str(event_request_id), str(registration_id), caller.id, now
    )
