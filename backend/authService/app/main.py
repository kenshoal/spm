from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from postgrest.exceptions import APIError
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
    roles: list[str]


Role = Literal[
    "admin",
    "attendee",
    "event_coordinator",
    "event_operations_manager",
    "event_organiser",
    "technical_support",
    "venue_staff",
]

DEFAULT_ROLE = "attendee"
ADMIN_ROLE = "admin"
EVENT_OPERATIONS_MANAGER_ROLE = "event_operations_manager"


class RoleUpdateRequest(BaseModel):
    role: Role


class RoleUpdateResponse(BaseModel):
    id: str
    email: str | None
    role: str


class UserSummary(BaseModel):
    id: str
    email: str | None


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


def _roles_of(user) -> list[str]:
    metadata = user.app_metadata or {}
    roles = metadata.get("roles")
    if isinstance(roles, list):
        clean_roles = [role for role in roles if isinstance(role, str)]
        if clean_roles:
            return clean_roles
    role = metadata.get("role")
    return [role] if isinstance(role, str) and role else [DEFAULT_ROLE]


def _staff_roles_of(user, admin_client: Client | None = None) -> list[str]:
    if admin_client is None:
        return _roles_of(user)

    try:
        response = (
            admin_client.table("staff_roles")
            .select("role")
            .eq("user_id", user.id)
            .execute()
        )
    except APIError as error:
        if error.code == "PGRST205":
            return _roles_of(user)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Role store unavailable"
        ) from error
    roles = [row["role"] for row in response.data if isinstance(row.get("role"), str)]
    return roles or _roles_of(user)


def get_admin_client() -> Client:
    try:
        return get_supabase_admin_client()
    except ValueError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Role assignment is not configured"
        ) from error


def get_optional_admin_client() -> Client | None:
    try:
        return get_supabase_admin_client()
    except ValueError:
        return None


@app.get("/auth/me", response_model=AuthenticatedUser, tags=["auth"])
def current_user(
    supabase: Annotated[Client, Depends(get_supabase_client)],
    response: Response,
    admin_client: Annotated[Client | None, Depends(get_optional_admin_client)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    user = _verify_bearer(supabase, authorization)
    response.headers["Cache-Control"] = "no-store"
    roles = _staff_roles_of(user, admin_client)
    return AuthenticatedUser(
        id=user.id, email=user.email, role=roles[0], roles=roles
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
    caller_roles = _staff_roles_of(caller, admin_client)
    can_assign_any = ADMIN_ROLE in caller_roles
    can_assign_coordinator = EVENT_OPERATIONS_MANAGER_ROLE in caller_roles
    if not can_assign_any and not (
        can_assign_coordinator and payload.role == "event_coordinator"
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Insufficient permissions"
        )

    try:
        response = admin_client.auth.admin.get_user_by_id(user_id)
        if response.user is None:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "Authentication provider returned no user",
            )
        admin_client.table("staff_roles").upsert(
            {
                "user_id": user_id,
                "role": payload.role,
                "assigned_by": caller.id,
            }
        ).execute()
        roles = _staff_roles_of(response.user, admin_client)
        admin_client.auth.admin.update_user_by_id(
            user_id, {"app_metadata": {"role": roles[0], "roles": roles}}
        )
    except APIError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Role store unavailable"
        ) from error
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
    return RoleUpdateResponse(
        id=response.user.id,
        email=response.user.email,
        role=roles[0],
    )


@app.get("/auth/users", response_model=list[UserSummary], tags=["auth"])
def list_users_by_role(
    role: Role,
    supabase: Annotated[Client, Depends(get_supabase_client)],
    admin_client: Annotated[Client, Depends(get_admin_client)],
    authorization: Annotated[str | None, Header()] = None,
) -> list[UserSummary]:
    caller = _verify_bearer(supabase, authorization)
    caller_roles = _staff_roles_of(caller, admin_client)
    can_list_any = ADMIN_ROLE in caller_roles
    can_list_coordinators = EVENT_OPERATIONS_MANAGER_ROLE in caller_roles
    if not can_list_any and not (
        can_list_coordinators and role == "event_coordinator"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")

    try:
        rows = (
            admin_client.table("staff_roles")
            .select("user_id")
            .eq("role", role)
            .execute()
            .data
        )
    except APIError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Role store unavailable"
        ) from error

    user_ids = sorted(
        {row["user_id"] for row in rows if isinstance(row.get("user_id"), str)}
    )
    users: list[UserSummary] = []
    for user_id in user_ids:
        try:
            found = admin_client.auth.admin.get_user_by_id(user_id).user
        except AuthApiError as error:
            if error.status == status.HTTP_404_NOT_FOUND:
                continue  # A role row outlived its account; nothing to offer.
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
            ) from error
        except AuthError as error:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
            ) from error
        if found is not None:
            users.append(UserSummary(id=found.id, email=found.email))
    return sorted(users, key=lambda user: (user.email or "", user.id))
