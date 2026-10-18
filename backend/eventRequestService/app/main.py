import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

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
from app.models.event_request import HealthResponse
from app.repositories import EventRequestRepository, SupabaseRepositoryError
from app.repositories.coordinator_assignment_repository import (
    CoordinatorAssignmentRepository,
)
from app.services.arrangement_review_notification_relay import (
    ArrangementReviewNotificationRelay,
    build_arrangement_review_notification_relay,
)
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
    SafetyDecisionInvalidError,
    TransitionForbiddenError,
    TransitionNotAllowedError,
)
from app.services.outbox_relay import OutboxRelay, build_outbox_relay


def create_app(
    repository: EventRequestRepository | None = None,
    coordinator_repository: CoordinatorAssignmentRepository | None = None,
    outbox_relay: OutboxRelay | None = None,
    arrangement_review_relay: ArrangementReviewNotificationRelay | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        relay_tasks = [
            asyncio.create_task(relay.run_forever())
            for relay in (outbox_relay, arrangement_review_relay)
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
        EventRequestService(repository) if repository is not None else None
    )
    coordinator_assignment_service = (
        CoordinatorAssignmentService(coordinator_repository, event_request_service)
        if coordinator_repository is not None and event_request_service is not None
        else None
    )
    application.state.event_request_service = event_request_service
    application.state.coordinator_assignment_service = coordinator_assignment_service
    application.state.event_transition_service = (
        EventTransitionService(event_request_service)
        if event_request_service is not None
        else None
    )
    # Before event_request_router: routes match in registration order, and its
    # /event-requests/{event_request_id} would otherwise swallow the literal
    # /event-requests/awaiting-assignment and reject it as a malformed UUID.
    application.include_router(coordinator_assignment_router)
    application.include_router(event_transition_router)
    application.include_router(event_request_router)
    application.include_router(arrangement_review_router)

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

    @application.exception_handler(SafetyDecisionInvalidError)
    async def safety_decision_invalid(
        request: Request, error: SafetyDecisionInvalidError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(error)},
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
)
