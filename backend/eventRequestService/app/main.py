from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.controllers.event_request_controller import router as event_request_router
from app.models.event_request import HealthResponse
from app.repositories import EventRequestRepository, SupabaseRepositoryError
from app.services.event_request_service import (
    EventRequestNotDraftError,
    EventRequestNotFoundError,
    EventRequestService,
)


def create_app(repository: EventRequestRepository | None = None) -> FastAPI:
    application = FastAPI(
        title="eventRequestService",
        description="Create and manage event requests.",
        version="0.1.0",
    )
    application.state.event_request_service = (
        EventRequestService(repository) if repository is not None else None
    )
    application.include_router(event_request_router)

    @application.exception_handler(EventRequestNotFoundError)
    async def event_request_not_found(
        request: Request, error: EventRequestNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
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
