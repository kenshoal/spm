from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.controllers.event_request_controller import router as event_request_router
from app.models.event_request import HealthResponse
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)


def create_app(database_path: str | Path | None = None) -> FastAPI:
    application = FastAPI(
        title="eventRequestService",
        description="Create and manage event requests.",
        version="0.1.0",
    )
    application.state.event_request_service = EventRequestService(database_path)
    application.include_router(event_request_router)

    @application.exception_handler(EventRequestNotFoundError)
    async def event_request_not_found(
        request: Request, error: EventRequestNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(error)},
        )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service="eventRequestService", status="ok")

    return application


app = create_app()

