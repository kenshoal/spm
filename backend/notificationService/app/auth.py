import hmac
import os
from typing import Annotated
from uuid import UUID

import httpx2
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from app.config import get_settings

# A declared security scheme, not a plain header parameter: Swagger UI never
# sends a header parameter named Authorization, so /docs needs this to show an
# Authorize button that does. It also reads the scheme case-insensitively.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="The access_token from authService's POST /auth/login.",
)


INTERNAL_TOKEN_HEADER = "X-Internal-Token"


def require_internal_caller(
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """Only ConnectSphere's own services may send notification events.

    They hold a shared secret from the environment. With none configured every
    sender is refused, so a missing setting cannot leave the endpoint open.
    """
    expected = os.environ.get("NOTIFICATION_INTERNAL_TOKEN", "")
    if not expected or not hmac.compare_digest(
        (x_internal_token or "").encode(), expected.encode()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Internal token required")


def get_current_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> str:
    """Return the id authService verifies for the caller's bearer token.

    Same check as eventRequestService: the token is never decoded here, only
    passed to authService's /auth/me, so there is one source of truth for who
    is signed in.
    """
    token = credentials.credentials.strip() if credentials else ""
    if not token or " " in token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    try:
        auth_service_url = str(get_settings().auth_service_url).rstrip("/")
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "notificationService is not configured"
        ) from error
    try:
        response = httpx2.get(
            f"{auth_service_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx2.HTTPError as error:
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
        return str(UUID(response.json()["id"]))
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service returned no user"
        ) from error
