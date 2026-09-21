from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.routers import block_checks, venues
from app.supabase_repository import StorageError


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
app.include_router(block_checks.router)


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
