from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from supabase import Client
from supabase_auth.errors import AuthApiError, AuthError

from app.integrations import get_supabase_admin_client, get_supabase_client


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
    role: str


Role = Literal[
    "admin", "technical_support", "event_coordinator", "venue_staff", "operations_manager"
]

DEFAULT_ROLE = "event_coordinator"
ADMIN_ROLE = "admin"


class RoleUpdateRequest(BaseModel):
    role: Role


class RoleUpdateResponse(BaseModel):
    id: str
    email: str | None
    role: str


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


def _verify_bearer(supabase: Client, authorization: str | None):
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
    return auth_response.user


def _role_of(user) -> str:
    return (user.app_metadata or {}).get("role", DEFAULT_ROLE)


def get_admin_client() -> Client:
    try:
        return get_supabase_admin_client()
    except ValueError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Role assignment is not configured"
        ) from error


@app.get("/auth/me", response_model=AuthenticatedUser, tags=["auth"])
def current_user(
    supabase: Annotated[Client, Depends(get_supabase_client)],
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    user = _verify_bearer(supabase, authorization)
    response.headers["Cache-Control"] = "no-store"
    return AuthenticatedUser(
        id=user.id, email=user.email, role=_role_of(user)
    )


@app.patch(
    "/auth/users/{user_id}/role",
    response_model=RoleUpdateResponse,
    tags=["auth"],
)
def update_user_role(
    user_id: str,
    payload: RoleUpdateRequest,
    supabase: Annotated[Client, Depends(get_supabase_client)],
    admin_client: Annotated[Client, Depends(get_admin_client)],
    authorization: Annotated[str | None, Header()] = None,
) -> RoleUpdateResponse:
    caller = _verify_bearer(supabase, authorization)
    if _role_of(caller) != ADMIN_ROLE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Insufficient permissions"
        )

    try:
        response = admin_client.auth.admin.update_user_by_id(
            user_id, {"app_metadata": {"role": payload.role}}
        )
    except AuthApiError as error:
        if error.status == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "User not found"
            ) from error
        if 400 <= error.status < 500:
            raise HTTPException(error.status, error.message) from error
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
        ) from error
    except AuthError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
        ) from error
    if response.user is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Authentication provider returned no user",
        )

    return RoleUpdateResponse(
        id=response.user.id,
        email=response.user.email,
        role=(response.user.app_metadata or {}).get("role", payload.role),
    )
