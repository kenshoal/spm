from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError

from app.config import get_settings
from app.models.event_request import (
    EventRequestCreate,
    EventRequestResponse,
    EventRequestSubmission,
    EventRequestUpdate,
)
from app.repositories import SupabaseEventRequestRepository
from app.services.event_request_service import EventRequestService

router = APIRouter(prefix="/event-requests", tags=["event requests"])


def get_event_request_service(request: Request) -> EventRequestService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.event_request_service
    if service is not None:
        return service

    try:
        repository = SupabaseEventRequestRepository.from_settings(get_settings())
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured for eventRequestService",
        ) from error

    service = EventRequestService(repository)
    request.app.state.event_request_service = service
    return service


def get_organiser_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Resolve the organiser from a validated Supabase session, not a caller ID."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    try:
        auth_service_url = str(get_settings().auth_service_url).rstrip("/")
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "eventRequestService is not configured"
        ) from error
    try:
        response = httpx.get(
            f"{auth_service_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service unavailable"
        ) from error
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if not response.is_success:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service unavailable"
        )
    try:
        return str(UUID(response.json()["id"]))
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service returned no user"
        ) from error


ServiceDependency = Annotated[EventRequestService, Depends(get_event_request_service)]
OrganiserDependency = Annotated[str, Depends(get_organiser_id)]


@router.post(
    "",
    response_model=EventRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event_request(
    payload: EventRequestCreate,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.create(payload, organiser_id)


@router.post(
    "/submissions",
    response_model=EventRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_new_event_request(
    payload: EventRequestSubmission,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.create_submission(payload, organiser_id)


@router.get("", response_model=list[EventRequestResponse])
def list_event_requests(
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> list[EventRequestResponse]:
    return service.list_for_organiser(organiser_id)


@router.get("/{event_request_id}", response_model=EventRequestResponse)
def get_event_request(
    event_request_id: UUID,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.get(str(event_request_id), organiser_id)


@router.patch("/{event_request_id}", response_model=EventRequestResponse)
def update_event_request(
    event_request_id: UUID,
    payload: EventRequestUpdate,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.update(str(event_request_id), organiser_id, payload)


@router.post("/{event_request_id}/submit", response_model=EventRequestResponse)
def submit_draft_event_request(
    event_request_id: UUID,
    payload: EventRequestSubmission,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.submit(str(event_request_id), organiser_id, payload)


@router.delete("/{event_request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_request(
    event_request_id: UUID,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> Response:
    service.delete(str(event_request_id), organiser_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
