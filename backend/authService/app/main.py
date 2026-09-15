from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.integrations import get_supabase_client


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


class RegisterRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class RegisteredUser(BaseModel):
    id: str
    email: str | None
    email_confirmation_required: bool


app = FastAPI(
    title="authService",
    description="Supabase-backed authentication microservice for SPM.",
    version="0.1.0",
)


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="authService",
        message="Hello from authService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="authService", status="ok")


@app.post(
    "/auth/register",
    response_model=RegisteredUser,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
def register(
    credentials: RegisterRequest,
    supabase: Annotated[Client, Depends(get_supabase_client)],
) -> RegisteredUser:
    try:
        response = supabase.auth.sign_up(credentials.model_dump())
    except AuthApiError as error:
        if 400 <= error.status < 500:
            raise HTTPException(error.status, error.message) from error
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Authentication provider unavailable",
        ) from error

    if response.user is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Authentication provider returned no user",
        )

    return RegisteredUser(
        id=response.user.id,
        email=response.user.email,
        email_confirmation_required=response.session is None,
    )
