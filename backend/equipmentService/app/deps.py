# Auth seam: identity and role come from authService's /auth/me, verified
# against Supabase (see docs/AUTH_INTEGRATION.md).
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, ValidationError

from app.config import get_settings

TECHNICAL_SUPPORT_ROLE = "technical_support"
EVENT_COORDINATOR_ROLE = "event_coordinator"
SAFETY_OFFICER_ROLE = "safety_officer"


class User(BaseModel):
    id: str
    roles: list[str]


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    try:
        auth_service_url = str(get_settings().auth_service_url).rstrip("/")
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Service is not configured"
        ) from error
    try:
        response = httpx.get(
            f"{auth_service_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service unavailable"
        ) from error
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if not response.is_success:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service unavailable"
        )
    try:
        return User(
            id=str(UUID(response.json()["id"])),
            roles=response.json().get("roles") or [response.json()["role"]],
        )
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service returned no user"
        ) from error


def require_role(*allowed: str):
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not set(user.roles).intersection(allowed):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return dependency
