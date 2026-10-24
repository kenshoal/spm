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
from app.models.registration import PublicEventResponse, RegistrationResponse
from app.repositories.registration_repository import SupabaseRegistrationRepository
from app.services.registration_service import RegistrationService

router = APIRouter(prefix="/attendee", tags=["attendee registration"])
ATTENDEE_ROLE = "attendee"


def get_registration_service(request: Request) -> RegistrationService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.registration_service
    if service is not None:
        return service

    try:
        repository = SupabaseRegistrationRepository.from_settings(get_settings())
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured for eventRequestService",
        ) from error

    service = RegistrationService(repository)
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


@router.post(
    "/registrations/{registration_id}/withdrawal",
    response_model=RegistrationResponse,
)
def withdraw_registration(
    registration_id: UUID,
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
    now: NowDependency,
) -> dict:
    return service.withdraw(str(registration_id), attendee_id, now)
