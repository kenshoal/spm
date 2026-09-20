from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.config import get_settings
from app.controllers.event_request_controller import (
    get_event_request_service,
    get_organiser_id,
)
from app.models.coordinator_assignment import (
    CoordinatorAssignmentResponse,
    CoordinatorAssignRequest,
)
from app.repositories.coordinator_assignment_repository import (
    SupabaseCoordinatorAssignmentRepository,
)
from app.services.coordinator_assignment_service import CoordinatorAssignmentService
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
    """Like get_organiser_id, but also requires the operations_manager role
    from authService's app_metadata. Duplicates get_organiser_id's session
    verification rather than sharing it, so this file stays self-contained
    and event_request_controller.py — Heng Rui's — doesn't need to change.
    """
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
        body = response.json()
        caller_id = str(UUID(body["id"]))
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service returned no user"
        ) from error

    if body.get("role") != "operations_manager":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only an Event Operations Manager can assign a Coordinator",
        )
    return caller_id


ServiceDependency = Annotated[
    CoordinatorAssignmentService, Depends(get_coordinator_assignment_service)
]
# Reused as-is from event_request_controller: resolves any verified caller's
# id, with no role check. Fine for GET (read-only, matches the original
# eventService prototype, which required no auth at all here) — not fine for
# POST, which uses get_operations_manager_id below instead.
CallerDependency = Annotated[str, Depends(get_organiser_id)]
OperationsManagerDependency = Annotated[str, Depends(get_operations_manager_id)]


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
    _caller: CallerDependency,
    service: ServiceDependency,
) -> CoordinatorAssignmentResponse:
    return service.get_current(event_request_id)
