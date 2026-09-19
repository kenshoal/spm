from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from supabase import Client
from supabase_auth.errors import AuthApiError, AuthError

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


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str


class AuthenticatedUser(BaseModel):
    id: str
    email: str | None
    # Server-controlled authorization claim, e.g. "operations_manager" —
    # stored in Supabase's app_metadata (not user_metadata, which the user
    # can edit themselves). None until something actually sets it; setting
    # it requires the service-role key, which this service doesn't hold —
    # for now that's a manual step in the Supabase dashboard.
    role: str | None = None


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
    except AuthError as error:
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


@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(
    credentials: LoginRequest,
    supabase: Annotated[Client, Depends(get_supabase_client)],
    response: Response,
) -> LoginResponse:
    try:
        auth_response = supabase.auth.sign_in_with_password(credentials.model_dump())
    except AuthApiError as error:
        if error.code == "email_not_confirmed":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Email confirmation required"
            ) from error
        if error.status == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(error.status, "Too many login attempts") from error
        if 400 <= error.status < 500:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid email or password"
            ) from error
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Authentication provider unavailable",
        ) from error
    except AuthError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Authentication provider unavailable",
        ) from error

    if auth_response.session is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Authentication provider returned no session",
        )

    response.headers["Cache-Control"] = "no-store"
    return LoginResponse.model_validate(auth_response.session, from_attributes=True)


@app.get("/auth/me", response_model=AuthenticatedUser, tags=["auth"])
def current_user(
    supabase: Annotated[Client, Depends(get_supabase_client)],
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    try:
        auth_response = supabase.auth.get_user(token)
    except AuthApiError as error:
        if 400 <= error.status < 500:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from error
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
        ) from error
    except AuthError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
        ) from error
    if auth_response.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    response.headers["Cache-Control"] = "no-store"
    # getattr, not .app_metadata: existing test doubles construct a bare
    # SimpleNamespace(id=..., email=...) with no app_metadata at all.
    app_metadata = getattr(auth_response.user, "app_metadata", None) or {}
    role = app_metadata.get("role")
    return AuthenticatedUser(
        id=auth_response.user.id, email=auth_response.user.email, role=role
    )
