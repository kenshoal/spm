from fastapi import FastAPI
from pydantic import BaseModel

from app.routers import assignments


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="eventService",
    description=(
        "Coordinator-assignment microservice for SPM. Event data, drafting, "
        "and status all live in eventRequestService — this service only "
        "owns who's assigned to coordinate a submitted event request."
    ),
    version="0.1.0",
)

app.include_router(assignments.router)


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="eventService",
        message="Hello from eventService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="eventService", status="ok")
