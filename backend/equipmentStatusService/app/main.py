from fastapi import FastAPI
from pydantic import BaseModel

from app.routers import status


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="equipmentStatusService",
    description="Equipment status microservice for SPM (SCRUM-16).",
    version="0.1.0",
)

app.include_router(status.router)


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="equipmentStatusService",
        message="Hello from equipmentStatusService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="equipmentStatusService", status="ok")
