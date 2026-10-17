from fastapi import FastAPI
from pydantic import BaseModel

from app.routers import availability, equipment, requirements, reservations, status


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="equipmentService",
    description="Equipment catalogue & status microservice for SPM (SCRUM-10, SCRUM-13, SCRUM-16, SCRUM-33, SCRUM-45).",
    version="0.1.0",
)

app.include_router(equipment.router)
app.include_router(status.router)
app.include_router(availability.router)
app.include_router(requirements.router)
app.include_router(reservations.router)


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="equipmentService",
        message="Hello from equipmentService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="equipmentService", status="ok")
