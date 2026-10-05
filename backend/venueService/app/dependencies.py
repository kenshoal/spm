"""Authentication and role checks delegated to authService."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, status


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: tuple[str, ...]


def require_authenticated(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or " " in token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    try:
        response = httpx.get(
            f"{os.getenv('AUTH_SERVICE_URL', 'http://127.0.0.1:8001').rstrip('/')}/auth/me",
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
        user = response.json()
        roles = user.get("roles") or [user["role"]]
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            raise TypeError
        return Principal(str(UUID(user["id"])), tuple(roles))
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Authentication service returned no user",
        ) from error


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    """The caller's raw token, to forward to another service on their behalf."""

    return (authorization or "").removeprefix("Bearer ").strip()


def require_event_coordinator(
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> Principal:
    if "event_coordinator" not in principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return principal


def require_booking_reader(
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> Principal:
    if not {"venue_staff", "event_coordinator"} & set(principal.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return principal


def require_venue_staff(
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> Principal:
    if "venue_staff" not in principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return principal
