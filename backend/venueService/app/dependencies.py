"""Authorisation dependencies.

These are placeholders. The briefing requires role-based access (Venue Staff
maintain the catalogue; authorised internal users may read it), but the auth
service is a separate scaffold and no shared token verification exists yet.
Each function currently returns a stub principal so the endpoint contracts
express who is meant to call them.

TODO: replace with real verification against authService — validate the bearer
token and confirm the caller's role.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


def require_venue_staff() -> Principal:
    """Caller must be Venue Staff (create / update catalogue records)."""

    return Principal(user_id="stub-venue-staff", role="venue_staff")


def require_authenticated() -> Principal:
    """Caller must be an authenticated internal user (read / search)."""

    return Principal(user_id="stub-internal-user", role="event_coordinator")
