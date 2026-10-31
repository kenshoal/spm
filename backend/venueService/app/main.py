import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.booking_notifications import get_booking_notifier
from app.config import get_settings
from app.hold_expiry import run_forever
from app.hold_store import get_hold_store
from app.routers import (
    block_checks,
    booking_decisions,
    booking_requests,
    suitability,
    venue_calendar,
    venue_holds,
    venues,
)
from app.supabase_block_repository import StorageError
from app.supabase_repository import SupabaseRepositoryError


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Sweep expired venue holds in the background (SCRUM-18). Only with
    Supabase storage: memory storage is for tests and resets on restart."""
    settings = get_settings()
    task = None
    if settings.venue_storage_backend == "supabase" and settings.venue_hold_sweep_seconds > 0:
        task = asyncio.create_task(
            run_forever(get_hold_store(), get_booking_notifier(), settings.venue_hold_sweep_seconds)
        )
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="venueService",
    description="Venue catalogue and search microservice for SPM.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(venues.router)
app.include_router(block_checks.router)
app.include_router(booking_requests.router)
app.include_router(booking_decisions.router)
app.include_router(suitability.router)
app.include_router(venue_calendar.router)
app.include_router(venue_holds.router)


@app.exception_handler(SupabaseRepositoryError)
async def venue_store_unavailable(
    request: Request, error: SupabaseRepositoryError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(error)},
    )


@app.exception_handler(StorageError)
async def storage_error(request: Request, error: StorageError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": str(error)})


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="venueService",
        message="Hello from venueService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="venueService", status="ok")
