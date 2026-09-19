from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.controllers.coordinator_assignment_controller import (
    router as coordinator_assignment_router,
)
from app.controllers.event_request_controller import router as event_request_router
from app.models.event_request import HealthResponse
from app.repositories import EventRequestRepository, SupabaseRepositoryError
from app.repositories.coordinator_assignment_repository import (
    CoordinatorAssignmentRepository,
)
from app.services.coordinator_assignment_service import (
    CoordinatorAssignmentNotAllowedError,
    CoordinatorAssignmentNotFoundError,
    CoordinatorAssignmentService,
)
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)


def create_app(
    repository: EventRequestRepository | None = None,
    coordinator_repository: CoordinatorAssignmentRepository | None = None,
) -> FastAPI:
    application = FastAPI(
        title="eventRequestService",
        description="Create and manage event requests.",
        version="0.1.0",
    )
    event_request_service = (
        EventRequestService(repository) if repository is not None else None
    )
    application.state.event_request_service = event_request_service
    application.state.coordinator_assignment_service = (
        CoordinatorAssignmentService(coordinator_repository, event_request_service)
        if coordinator_repository is not None and event_request_service is not None
        else None
    )
    application.include_router(event_request_router)
    application.include_router(coordinator_assignment_router)

    @application.exception_handler(EventRequestNotFoundError)
    async def event_request_not_found(
        request: Request, error: EventRequestNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
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


app = create_app()
