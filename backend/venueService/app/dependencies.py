"""Authorisation dependencies.

These are placeholders. The briefing requires role-based access (Venue Staff
maintain the catalogue; authorised internal users may read it), but the auth
service is a separate scaffold and no shared token verification exists yet.
Memory mode returns a stub principal. Database mode requires explicit local
development opt-in and uses a configured existing test user as the staff
principal. Neither path verifies tokens or roles yet.

TODO: replace with real verification against authService — validate the bearer
token and confirm the caller's role.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException

from app.config import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


def _check_development_access(settings: Settings) -> None:
    if (
        settings.venue_storage_backend == "supabase"
        and not settings.venue_allow_stub_auth
    ):
        raise HTTPException(
            503,
            "Authentication is not integrated. Local testing requires "
            "VENUE_ALLOW_STUB_AUTH=true; do not expose this development server.",
        )


def require_venue_staff(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Caller must be Venue Staff (create / update catalogue records)."""

    _check_development_access(settings)
    if settings.venue_storage_backend == "supabase":
        if settings.venue_dev_staff_user_id is None:
            raise HTTPException(
                503,
                "Set VENUE_DEV_STAFF_USER_ID to an existing test user's UUID "
                "until real staff authentication is integrated",
            )
        return Principal(
            user_id=str(settings.venue_dev_staff_user_id), role="venue_staff"
        )
    return Principal(user_id="stub-venue-staff", role="venue_staff")


def require_authenticated(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Caller must be an authenticated internal user (read / search)."""

    _check_development_access(settings)
    return Principal(user_id="stub-internal-user", role="event_coordinator")
