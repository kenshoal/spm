from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError

from app.config import get_settings
from app.models.event_request import (
    AttendeeEventResponse,
    EventChangeDecision,
    EventChangeRequestCreate,
    EventChangeRequestResponse,
    EventClarificationResponse,
    EventRequestCreate,
    EventRequestResponse,
    EventRequestStatus,
    EventRequestSubmission,
    EventRequestUpdate,
    EventReviewDecisionResponse,
)
from app.repositories import SupabaseEventRequestRepository
from app.services.coordinator_assignment_service import (
    CoordinatorAssignmentNotFoundError,
)
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)

router = APIRouter(prefix="/event-requests", tags=["event requests"])
EVENT_ORGANISER_ROLE = "event_organiser"
EVENT_COORDINATOR_ROLE = "event_coordinator"

_PUBLIC_STATUSES = {EventRequestStatus.CONFIRMED, EventRequestStatus.COMPLETED}


@dataclass(frozen=True)
class AuthenticatedCaller:
    id: str
    roles: tuple[str, ...]


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


def get_authenticated_caller(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedCaller:
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
        user = response.json()
        roles = user.get("roles") or [user["role"]]
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            raise TypeError
        return AuthenticatedCaller(str(UUID(user["id"])), tuple(roles))
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service returned no user"
        ) from error


def get_authenticated_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    return get_authenticated_caller(authorization).id


def get_organiser_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    caller = get_authenticated_caller(authorization)
    if EVENT_ORGANISER_ROLE not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return caller.id


def get_coordinator_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    caller = get_authenticated_caller(authorization)
    if EVENT_COORDINATOR_ROLE not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return caller.id


ServiceDependency = Annotated[EventRequestService, Depends(get_event_request_service)]
OrganiserDependency = Annotated[str, Depends(get_organiser_id)]
CallerDependency = Annotated[AuthenticatedCaller, Depends(get_authenticated_caller)]
CoordinatorDependency = Annotated[str, Depends(get_coordinator_id)]


def _coordinator_assignment_service(request: Request):
    # Deferred import: coordinator_assignment_controller imports this module,
    # so a module-level import would be circular.
    from app.controllers.coordinator_assignment_controller import (
        get_coordinator_assignment_service,
    )

    return get_coordinator_assignment_service(request)


def _require_role(caller: AuthenticatedCaller, role: str) -> None:
    if role not in caller.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")


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


# Declared before GET /{event_request_id}: the UUID path param would otherwise
# swallow this literal path (FastAPI validates path params after routing, 422).
@router.get("/assigned-to-me", response_model=list[EventRequestResponse])
def list_requests_assigned_to_me(
    coordinator_id: CoordinatorDependency,
    request: Request,
) -> list[EventRequestResponse]:
    return _coordinator_assignment_service(request).list_requests_for_coordinator(
        coordinator_id
    )


@router.get("/public-events", response_model=list[AttendeeEventResponse])
def list_public_events(
    caller: CallerDependency,
    service: ServiceDependency,
) -> list[AttendeeEventResponse]:
    _require_role(caller, "attendee")
    return [
        AttendeeEventResponse.model_validate(request, from_attributes=True)
        for request in service.list_by_statuses(_PUBLIC_STATUSES)
    ]


@router.get("/{event_request_id}", response_model=EventRequestResponse)
def get_event_request(
    event_request_id: UUID,
    caller: CallerDependency,
    request: Request,
    service: ServiceDependency,
) -> EventRequestResponse:
    request_id = str(event_request_id)
    roles = set(caller.roles)

    if "event_organiser" in roles:
        try:
            return service.get_viewable(request_id, caller.id)
        except EventRequestNotFoundError:
            pass  # Not the owner — the caller's coordinator role may still grant access.

    if "event_coordinator" in roles:
        try:
            assignment = _coordinator_assignment_service(request).get_current(
                request_id
            )
        except CoordinatorAssignmentNotFoundError as error:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Event request not found"
            ) from error
        if assignment.coordinator_id == caller.id:
            return service.get_by_id(request_id)

    if roles.isdisjoint({"event_organiser", "event_coordinator"}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")


@router.get(
    "/{event_request_id}/decisions",
    response_model=list[EventReviewDecisionResponse],
)
def list_review_decisions(
    event_request_id: UUID,
    caller: CallerDependency,
    request: Request,
    service: ServiceDependency,
) -> list[EventReviewDecisionResponse]:
    """Expose decisions only to the owning organiser or assigned coordinator."""
    request_id = str(event_request_id)
    roles = set(caller.roles)

    if "event_organiser" in roles:
        try:
            service.get_viewable(request_id, caller.id)
            return service.list_review_decisions(request_id)
        except EventRequestNotFoundError:
            pass

    if "event_coordinator" in roles:
        try:
            assignment = _coordinator_assignment_service(request).get_current(
                request_id
            )
        except CoordinatorAssignmentNotFoundError as error:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Event request not found"
            ) from error
        if assignment.coordinator_id == caller.id:
            return service.list_review_decisions(request_id)

    if roles.isdisjoint({"event_organiser", "event_coordinator"}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")


@router.post(
    "/{event_request_id}/change-requests",
    response_model=EventChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_change_request(
    event_request_id: UUID,
    payload: EventChangeRequestCreate,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventChangeRequestResponse:
    return service.create_change_request(str(event_request_id), organiser_id, payload)


@router.get(
    "/{event_request_id}/change-requests",
    response_model=list[EventChangeRequestResponse],
)
def list_change_requests(
    event_request_id: UUID,
    caller: CallerDependency,
    request: Request,
    service: ServiceDependency,
) -> list[EventChangeRequestResponse]:
    request_id = str(event_request_id)
    roles = set(caller.roles)
    if EVENT_ORGANISER_ROLE in roles:
        try:
            service.get(request_id, caller.id)
            return service.list_change_requests(request_id)
        except EventRequestNotFoundError:
            pass
    if EVENT_COORDINATOR_ROLE in roles:
        try:
            assignment = _coordinator_assignment_service(request).get_current(request_id)
        except CoordinatorAssignmentNotFoundError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found") from error
        if assignment.coordinator_id == caller.id:
            return service.list_change_requests(request_id)
    if roles.isdisjoint({EVENT_ORGANISER_ROLE, EVENT_COORDINATOR_ROLE}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")


@router.post(
    "/{event_request_id}/change-requests/{change_request_id}/decision",
    response_model=EventChangeRequestResponse,
)
def decide_change_request(
    event_request_id: UUID,
    change_request_id: UUID,
    payload: EventChangeDecision,
    coordinator_id: CoordinatorDependency,
    service: ServiceDependency,
) -> EventChangeRequestResponse:
    return service.decide_change_request(
        str(event_request_id), str(change_request_id), coordinator_id, payload
    )


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


@router.post(
    "/{event_request_id}/clarification-response",
    response_model=EventReviewDecisionResponse,
)
def respond_to_clarification(
    event_request_id: UUID,
    payload: EventClarificationResponse,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventReviewDecisionResponse:
    return service.respond_to_clarification(
        str(event_request_id), organiser_id, payload
    )


@router.delete("/{event_request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_request(
    event_request_id: UUID,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> Response:
    service.delete(str(event_request_id), organiser_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
