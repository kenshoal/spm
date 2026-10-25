from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError

from app.config import get_settings
from app.models.arrangement_review import ArrangementReviewResponse
from app.models.event_request import (
    AttendeeEventResponse,
    EventChangeBookingContext,
    EventChangeDatePlanResponse,
    EventChangeDecision,
    EventChangeRequestCreate,
    EventChangeRequestResponse,
    EventChangeRequestStatus,
    EventClarificationResponse,
    EventFinalEndUpdate,
    EventRequestCreate,
    EventRequestResponse,
    EventRequestStatus,
    EventRequestSubmission,
    EventRequestUpdate,
    EventReviewDecisionResponse,
    EventStatusHistoryResponse,
)
from app.models.registration_review import RegistrationReviewResponse
from app.repositories import (
    EventRequestRpcError,
    SupabaseEventRequestRepository,
    SupabaseRepositoryError,
)
from app.services.coordinator_assignment_service import (
    CoordinatorAssignmentNotFoundError,
)
from app.services.event_request_service import (
    ArrangementReviewActionError,
    EventChangeBookingConflictError,
    EventChangeBookingPlanError,
    EventChangeDatePlanConflictError,
    EventRequestNotFoundError,
    EventRequestService,
)
from app.services.notification_client import NotificationClient

router = APIRouter(prefix="/event-requests", tags=["event requests"])
EVENT_ORGANISER_ROLE = "event_organiser"
EVENT_COORDINATOR_ROLE = "event_coordinator"
_NON_DATE_CHANGE_FIELDS = {
    "expected_attendance", "venue_requirements", "equipment_requirements", "registration_needs"
}

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

    service = EventRequestService(
        repository, NotificationClient.from_settings(get_settings())
    )
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


def _registration_review_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": "Registration review is not accessible"})


@router.get("/{event_request_id}/registration-reviews", response_model=list[RegistrationReviewResponse])
def list_registration_reviews(
    event_request_id: UUID, caller: CallerDependency, request: Request, service: ServiceDependency,
) -> list[RegistrationReviewResponse]:
    """Only the owning organiser or current coordinator may read retained evidence."""
    request_id = str(event_request_id)
    if EVENT_ORGANISER_ROLE in caller.roles:
        try:
            service.get(request_id, caller.id)
            return service.list_registration_reviews(request_id)
        except EventRequestNotFoundError:
            pass
    if EVENT_COORDINATOR_ROLE in caller.roles:
        try:
            assignment = _coordinator_assignment_service(request).get_current(request_id)
            if assignment.coordinator_id == caller.id:
                return service.list_registration_reviews(request_id)
        except (CoordinatorAssignmentNotFoundError, EventRequestNotFoundError):
            pass
    raise _registration_review_error(404, "REGISTRATION_REVIEW_NOT_FOUND")


@router.post("/{event_request_id}/registration-reviews/{review_id}/acknowledge", response_model=RegistrationReviewResponse)
def acknowledge_registration_review(
    event_request_id: UUID, review_id: UUID, caller: CallerDependency, service: ServiceDependency,
) -> RegistrationReviewResponse:
    # No body: the verified actor and locked current assignment are authoritative.
    if EVENT_COORDINATOR_ROLE not in caller.roles:
        raise _registration_review_error(403, "REGISTRATION_REVIEW_FORBIDDEN")
    try:
        return service.acknowledge_registration_review(str(event_request_id), str(review_id), caller.id)
    except ArrangementReviewActionError as error:
        status_code, code = {
            "P0002": (404, "REGISTRATION_REVIEW_NOT_FOUND"),
            "P0003": (403, "REGISTRATION_REVIEW_FORBIDDEN"),
            "P0004": (409, "REGISTRATION_REVIEW_ALREADY_ACKNOWLEDGED"),
        }[error.code]
        raise _registration_review_error(status_code, code) from error


@router.get(
    "/{event_request_id}/arrangement-reviews",
    response_model=list[ArrangementReviewResponse],
)
def list_arrangement_reviews(
    event_request_id: UUID,
    caller: CallerDependency,
    request: Request,
    service: ServiceDependency,
) -> list[ArrangementReviewResponse]:
    """Event-wide review evidence belongs only to its current coordinator."""
    if EVENT_COORDINATOR_ROLE not in caller.roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ARRANGEMENT_REVIEWS_FORBIDDEN",
                "message": "Arrangement reviews are not accessible",
            },
        )
    request_id = str(event_request_id)
    not_found = {
        "code": "ARRANGEMENT_REVIEWS_NOT_FOUND",
        "message": "Arrangement reviews are not accessible",
    }
    try:
        assignment = _coordinator_assignment_service(request).get_current(request_id)
    except (CoordinatorAssignmentNotFoundError, EventRequestNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=not_found) from error
    if assignment.coordinator_id != caller.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=not_found)
    return service.list_arrangement_reviews(request_id)


@router.get(
    "/{event_request_id}/status-history",
    response_model=list[EventStatusHistoryResponse],
)
def list_status_history(
    event_request_id: UUID,
    caller: CallerDependency,
    request: Request,
    service: ServiceDependency,
) -> list[EventStatusHistoryResponse]:
    """Reuse request visibility so the history cannot expand SCRUM-39 access."""
    try:
        get_event_request(event_request_id, caller, request, service)
    except HTTPException as error:
        if error.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND):
            code = "HISTORY_FORBIDDEN" if error.status_code == 403 else "HISTORY_NOT_FOUND"
            raise HTTPException(
                error.status_code,
                detail={"code": code, "message": "Status history is not accessible"},
            ) from error
        raise
    return service.list_status_history(str(event_request_id))

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


@router.get(
    "/{event_request_id}/change-requests/{change_request_id}/date-plan",
    response_model=EventChangeDatePlanResponse,
)
def preview_change_request_dates(
    event_request_id: UUID,
    change_request_id: UUID,
    coordinator_id: CoordinatorDependency,
    request: Request,
    service: ServiceDependency,
) -> EventChangeDatePlanResponse:
    request_id = str(event_request_id)
    try:
        assignment = _coordinator_assignment_service(request).get_current(request_id)
        if assignment.coordinator_id != coordinator_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only the assigned coordinator can access this change",
            )
        plan = service.plan_change_request_dates(request_id, str(change_request_id))
    except CoordinatorAssignmentNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found") from error
    except EventChangeDatePlanConflictError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": error.code, "message": "Date change plan is not available for this proposal."},
        ) from error
    except (SupabaseRepositoryError, ValidationError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Date change plan unavailable",
        ) from error
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found")
    return plan


@router.get(
    "/{event_request_id}/change-requests/{change_request_id}/booking-plan",
    response_model=EventChangeBookingContext,
)
def get_change_booking_context(
    event_request_id: UUID, change_request_id: UUID, coordinator_id: CoordinatorDependency,
    request: Request, service: ServiceDependency,
) -> EventChangeBookingContext:
    request_id = str(event_request_id)
    try:
        assignment = _coordinator_assignment_service(request).get_current(request_id)
        if assignment.coordinator_id != coordinator_id:
            raise HTTPException(403, "Only the assigned coordinator can access this change")
        plan = service.get_change_booking_context(request_id, str(change_request_id))
    except CoordinatorAssignmentNotFoundError as error:
        raise HTTPException(404, "Event request not found") from error
    except EventChangeDatePlanConflictError as error:
        raise HTTPException(409, detail={"code": error.code, "message": "Date change plan is not available for this proposal."}) from error
    except (SupabaseRepositoryError, ValidationError) as error:
        raise HTTPException(502, "Date change plan unavailable") from error
    if plan is None:
        raise HTTPException(404, "Change request not found")
    return plan


@router.post(
    "/{event_request_id}/change-requests/{change_request_id}/decision",
    response_model=EventChangeRequestResponse,
)
def decide_change_request(
    event_request_id: UUID,
    change_request_id: UUID,
    payload: EventChangeDecision,
    coordinator_id: CoordinatorDependency,
    request: Request,
    service: ServiceDependency,
) -> EventChangeRequestResponse:
    request_id = str(event_request_id)
    try:
        assignment = _coordinator_assignment_service(request).get_current(request_id)
    except CoordinatorAssignmentNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found") from error
    if assignment.coordinator_id != coordinator_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assigned coordinator can access this change")
    change = next(
        (
            change for change in service.list_change_requests(request_id)
            if change.id == str(change_request_id)
        ),
        None,
    )
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found")
    has_dates = "proposed_date_times" in change.proposed_changes
    if payload.booking_plan is not None and not has_dates:
        raise HTTPException(422, "Booking plan is only supported for date approval")
    if (
        payload.decision == EventChangeRequestStatus.APPROVED
        and has_dates
        and set(change.proposed_changes) <= (_NON_DATE_CHANGE_FIELDS | {"proposed_date_times"})
    ):
        try:
            return service.approve_date_change_request(
                request_id, str(change_request_id), coordinator_id, payload,
            )
        except EventChangeBookingConflictError as error:
            raise HTTPException(409, detail={
                "code": "BOOKING_CONFLICT", "message": str(error),
                "bookings": [booking.model_dump(mode="json") for booking in error.bookings],
            }) from error
        except EventChangeBookingPlanError as error:
            raise HTTPException(422, str(error)) from error
    # Refuse the whole proposal when any field needs an unsupported workflow.
    # The narrow RPC rechecks scope and current state under the event lock.
    supported_approval = (
        bool(change.proposed_changes)
        and set(change.proposed_changes) <= _NON_DATE_CHANGE_FIELDS
    )
    if payload.decision == EventChangeRequestStatus.REJECTED or supported_approval:
        return service.decide_change_request(
            request_id, str(change_request_id), coordinator_id, payload
        )
    # Unsupported proposals are never partially applied.
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail={
            "code": "CHANGE_DECISIONS_UNAVAILABLE",
            "message": "This proposal contains unsupported changes.",
        },
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


@router.post("/{event_request_id}/final-end", response_model=EventRequestResponse)
def set_event_final_end(
    event_request_id: UUID,
    payload: EventFinalEndUpdate,
    coordinator_id: CoordinatorDependency,
    service: ServiceDependency,
    request: Request,
) -> EventRequestResponse:
    """Record only an explicit coordinator end; never infer it from bookings."""
    request_id = str(event_request_id)
    try:
        assignment = _coordinator_assignment_service(request).get_current(request_id)
        if assignment.coordinator_id != coordinator_id:
            raise HTTPException(403, "Only the assigned coordinator can record the final end")
        return service.set_final_end(request_id, coordinator_id, payload)
    except CoordinatorAssignmentNotFoundError as error:
        raise HTTPException(404, "Event request not found") from error
    except EventRequestRpcError as error:
        if error.errcode == "P0002":
            raise HTTPException(404, "Event request not found") from error
        if error.errcode == "P0003":
            raise HTTPException(403, "Only the assigned coordinator can record the final end") from error
        if error.errcode == "P0004":
            raise HTTPException(409, {
                "code": "final_end_unavailable",
                "message": "The final event end can only be recorded while Approved or Planning.",
            }) from error
        raise HTTPException(502, "Final event end unavailable") from error
    except (SupabaseRepositoryError, ValidationError) as error:
        raise HTTPException(502, "Final event end unavailable") from error
