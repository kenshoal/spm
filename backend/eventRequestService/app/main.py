import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.config import get_notification_settings, get_periodic_task_settings
from app.controllers.arrangement_review_controller import (
    router as arrangement_review_router,
)
from app.controllers.coordinator_assignment_controller import (
    router as coordinator_assignment_router,
)
from app.controllers.event_request_controller import router as event_request_router
from app.controllers.event_transition_controller import (
    router as event_transition_router,
)
from app.controllers.registration_controller import (
    management_router as registration_info_router,
)
from app.controllers.registration_controller import router as registration_router
from app.controllers.technical_support_controller import (
    router as technical_support_router,
)
from app.models.event_request import HealthResponse
from app.repositories import EventRequestRepository, SupabaseRepositoryError
from app.repositories.coordinator_assignment_repository import (
    CoordinatorAssignmentRepository,
)
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.technical_support_repository import TechnicalSupportRepository
from app.services.arrangement_review_notification_relay import (
    ArrangementReviewNotificationRelay,
    build_arrangement_review_notification_relay,
)
from app.services.auto_completion import build_auto_completion_service
from app.services.coordinator_assignment_service import (
    CoordinatorAssignmentNotAllowedError,
    CoordinatorAssignmentNotFoundError,
    CoordinatorAssignmentService,
)
from app.services.event_request_service import (
    ClarificationResponseNotAllowedError,
    EventChangeRequestConflictError,
    EventChangeRequestForbiddenError,
    EventRequestForbiddenError,
    EventRequestNotDraftError,
    EventRequestNotFoundError,
    EventRequestService,
    EventRequestTransitionConflictError,
)
from app.services.event_transition_service import (
    DecisionReasonRequiredError,
    EventTransitionService,
    SafetyApprovalBlockedError,
    SafetyDecisionInvalidError,
    SafetyReviewNotReadyError,
    TransitionForbiddenError,
    TransitionNotAllowedError,
)
from app.services.notification_client import NotificationClient
from app.services.outbox_relay import OutboxRelay, build_outbox_relay
from app.services.periodic_task_runner import PeriodicTaskRunner
from app.services.registration_rules import (
    AlreadyWithdrawnError,
    EventFullError,
    EventNotVisibleError,
    RegistrationNotFoundError,
    RegistrationNotOpenError,
    WithdrawalNotPermittedError,
)
from app.services.registration_service import (
    AlreadyRegisteredError,
    AttendeeAlreadyRegisteredError,
    AttendeeNotFoundError,
    CapacityNotSetError,
    RegistrationService,
)
from app.services.technical_support_service import (
    TechnicalSupportError,
    TechnicalSupportService,
)


def build_periodic_task_runner() -> PeriodicTaskRunner | None:
    settings = get_periodic_task_settings()
    handlers = {}
    # Each story controls only its own registration. SCRUM-38 can add a separate
    # configured handler here even when automatic completion is disabled.
    if settings.auto_completion_enabled:
        completion = build_auto_completion_service()
        handlers["auto_completion"] = completion.run_once
    if not handlers:
        return None
    return PeriodicTaskRunner(
        handlers, interval_seconds=settings.periodic_task_interval_seconds
    )


def create_app(
    repository: EventRequestRepository | None = None,
    coordinator_repository: CoordinatorAssignmentRepository | None = None,
    outbox_relay: OutboxRelay | None = None,
    arrangement_review_relay: ArrangementReviewNotificationRelay | None = None,
    registration_repository: RegistrationRepository | None = None,
    technical_support_repository: TechnicalSupportRepository | None = None,
    technical_support_notification_client: NotificationClient | None = None,
    periodic_task_runner: PeriodicTaskRunner | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        relay_tasks = [
            asyncio.create_task(relay.run_forever())
            for relay in (outbox_relay, arrangement_review_relay, periodic_task_runner)
            if relay is not None
        ]
        try:
            yield
        finally:
            for task in relay_tasks:
                task.cancel()
            for task in relay_tasks:
                with suppress(asyncio.CancelledError):
                    await task

    application = FastAPI(
        title="eventRequestService",
        description="Create and manage event requests.",
        version="0.1.0",
        lifespan=lifespan,
    )
    event_request_service = (
        EventRequestService(
            repository, NotificationClient.from_settings(get_notification_settings())
        ) if repository is not None else None
    )
    coordinator_assignment_service = (
        CoordinatorAssignmentService(coordinator_repository, event_request_service)
        if coordinator_repository is not None and event_request_service is not None
        else None
    )
    application.state.event_request_service = event_request_service
    application.state.coordinator_assignment_service = coordinator_assignment_service
    application.state.registration_service = (
        RegistrationService(
            registration_repository,
            coordinator_repository,
            NotificationClient.from_settings(get_notification_settings()),
        )
        if registration_repository is not None
        else None
    )
    application.state.event_transition_service = (
        EventTransitionService(event_request_service)
        if event_request_service is not None
        else None
    )
    application.state.technical_support_service = (
        TechnicalSupportService(
            technical_support_repository,
            event_request_service,
            coordinator_repository,
            technical_support_notification_client,
        )
        if technical_support_repository is not None
        and event_request_service is not None
        and coordinator_repository is not None
        else None
    )
    # Before event_request_router: routes match in registration order, and its
    # /event-requests/{event_request_id} would otherwise swallow the literal
    # /event-requests/awaiting-assignment and reject it as a malformed UUID.
    # The same holds for event_transition_router's /event-requests/safety-queue
    # (SCRUM-60), so keep both routers above event_request_router.
    application.include_router(coordinator_assignment_router)
    application.include_router(event_transition_router)
    application.include_router(technical_support_router)
    application.include_router(event_request_router)
    application.include_router(arrangement_review_router)
    application.include_router(registration_router)
    application.include_router(registration_info_router)

    @application.exception_handler(EventRequestNotFoundError)
    async def event_request_not_found(
        request: Request, error: EventRequestNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(error)},
        )

    @application.exception_handler(EventRequestForbiddenError)
    async def event_request_forbidden(
        request: Request, error: EventRequestForbiddenError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(error)},
        )

    @application.exception_handler(EventRequestNotDraftError)
    async def event_request_not_draft(
        request: Request, error: EventRequestNotDraftError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    @application.exception_handler(ClarificationResponseNotAllowedError)
    async def clarification_response_not_allowed(
        request: Request, error: ClarificationResponseNotAllowedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    @application.exception_handler(EventChangeRequestConflictError)
    async def event_change_request_conflict(
        request: Request, error: EventChangeRequestConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    @application.exception_handler(EventChangeRequestForbiddenError)
    async def event_change_request_forbidden(
        request: Request, error: EventChangeRequestForbiddenError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(error)},
        )

    @application.exception_handler(CoordinatorAssignmentNotFoundError)
    async def coordinator_assignment_not_found(
        request: Request, error: CoordinatorAssignmentNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(error)},
        )

    @application.exception_handler(CoordinatorAssignmentNotAllowedError)
    async def coordinator_assignment_not_allowed(
        request: Request, error: CoordinatorAssignmentNotAllowedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    @application.exception_handler(EventRequestTransitionConflictError)
    async def event_request_transition_conflict(
        request: Request, error: EventRequestTransitionConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    @application.exception_handler(TransitionNotAllowedError)
    async def transition_not_allowed(
        request: Request, error: TransitionNotAllowedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    @application.exception_handler(SafetyReviewNotReadyError)
    async def safety_review_not_ready(
        request: Request, error: SafetyReviewNotReadyError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error), "outstanding": error.outstanding},
        )

    @application.exception_handler(TransitionForbiddenError)
    async def transition_forbidden(
        request: Request, error: TransitionForbiddenError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(error)},
        )

    @application.exception_handler(DecisionReasonRequiredError)
    async def decision_reason_required(
        request: Request, error: DecisionReasonRequiredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(error)},
        )

    @application.exception_handler(SafetyApprovalBlockedError)
    async def safety_approval_blocked(
        request: Request, error: SafetyApprovalBlockedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error), "outstanding": error.outstanding},
        )

    @application.exception_handler(SafetyDecisionInvalidError)
    async def safety_decision_invalid(
        request: Request, error: SafetyDecisionInvalidError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(error)},
        )

    @application.exception_handler(EventNotVisibleError)
    async def event_not_visible(
        request: Request, error: EventNotVisibleError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Event not found", "code": "event_not_found"},
        )

    @application.exception_handler(RegistrationNotOpenError)
    async def registration_not_open(
        request: Request, error: RegistrationNotOpenError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Registration is not open for this event",
                "code": "registration_not_open",
            },
        )

    @application.exception_handler(EventFullError)
    async def event_full(request: Request, error: EventFullError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "This event is full", "code": "event_full"},
        )

    @application.exception_handler(AlreadyRegisteredError)
    async def already_registered(
        request: Request, error: AlreadyRegisteredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "You are already registered for this event",
                "code": "already_registered",
            },
        )

    @application.exception_handler(AttendeeAlreadyRegisteredError)
    async def attendee_already_registered(
        request: Request, error: AttendeeAlreadyRegisteredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This attendee is already registered for this event",
                "code": "already_registered",
            },
        )

    @application.exception_handler(AttendeeNotFoundError)
    async def attendee_not_found(
        request: Request, error: AttendeeNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": "No attendee account has that email",
                "code": "attendee_not_found",
            },
        )

    @application.exception_handler(CapacityNotSetError)
    async def capacity_not_set(
        request: Request, error: CapacityNotSetError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This event has no registration capacity set",
                "code": "capacity_not_set",
            },
        )

    @application.exception_handler(RegistrationNotFoundError)
    async def registration_not_found(
        request: Request, error: RegistrationNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": "Registration not found",
                "code": "registration_not_found",
            },
        )

    @application.exception_handler(AlreadyWithdrawnError)
    async def already_withdrawn(
        request: Request, error: AlreadyWithdrawnError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This registration is already withdrawn",
                "code": "already_withdrawn",
            },
        )

    @application.exception_handler(WithdrawalNotPermittedError)
    async def withdrawal_not_permitted(
        request: Request, error: WithdrawalNotPermittedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This registration can no longer be withdrawn",
                "code": "withdrawal_not_permitted",
            },
        )

    # One handler renders every SCRUM-19 refusal: the error carries its own
    # code and HTTP status, so subclasses need no handler each (D12).
    @application.exception_handler(TechnicalSupportError)
    async def technical_support_refusal(
        request: Request, error: TechnicalSupportError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status,
            content={
                "detail": {"code": error.code, "message": str(error)},
            },
        )

    @application.exception_handler(SupabaseRepositoryError)
    async def supabase_unavailable(
        request: Request, error: SupabaseRepositoryError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(error)},
        )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service="eventRequestService", status="ok")

    return application


# Only the served app relays the outbox; apps built in tests get no relay unless
# they pass one, so a test run never delivers real events.
app = create_app(
    outbox_relay=build_outbox_relay(),
    arrangement_review_relay=build_arrangement_review_notification_relay(),
    periodic_task_runner=build_periodic_task_runner(),
)
