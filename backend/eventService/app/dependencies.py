"""Caller identity for request handlers.

Stubbed on headers until authService issues real tokens: trust
`X-User-Id` / `X-User-Role` as sent. Swap the body of `get_current_user`
for JWT verification later — the `Depends(get_current_user)` call sites in
routers do not need to change.
"""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import Header, HTTPException, status


class Role(StrEnum):
    ORGANISER = "organiser"
    EVENT_COORDINATOR = "event_coordinator"
    OPERATIONS_MANAGER = "operations_manager"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: Role


def get_current_user(
    x_user_id: str = Header(...),
    x_user_role: str = Header(...),
) -> CurrentUser:
    try:
        role = Role(x_user_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role: {x_user_role!r}",
        ) from exc
    return CurrentUser(id=x_user_id, role=role)
