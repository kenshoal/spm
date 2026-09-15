from fastapi import FastAPI
from pydantic import BaseModel

from app.routers import equipment


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="equipmentService",
    description="Equipment catalogue microservice for SPM (SCRUM-45).",
    version="0.1.0",
)

app.include_router(equipment.router)


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="equipmentService",
        message="Hello from equipmentService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="equipmentService", status="ok")
