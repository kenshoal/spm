from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.routers import booking_requests, bookings, suitability, venues
from app.supabase_repository import SupabaseRepositoryError


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="venueService",
    description="Venue catalogue and search microservice for SPM.",
    version="0.1.0",
)

app.include_router(venues.router)
app.include_router(booking_requests.router)
app.include_router(suitability.router)
app.include_router(bookings.router)


@app.exception_handler(SupabaseRepositoryError)
async def venue_store_unavailable(
    request: Request, error: SupabaseRepositoryError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(error)},
    )


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="venueService",
        message="Hello from venueService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="venueService", status="ok")
