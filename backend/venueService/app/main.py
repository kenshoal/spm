from fastapi import FastAPI
from pydantic import BaseModel

from app.routers import venues


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


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="venueService",
        message="Hello from venueService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="venueService", status="ok")
