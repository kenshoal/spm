from fastapi import FastAPI
from pydantic import BaseModel

from app.api.users import router as users_router


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="authService",
    description="Authentication microservice for SPM.",
    version="0.1.0",
)
app.include_router(users_router)


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="authService",
        message="Hello from authService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="authService", status="ok")
