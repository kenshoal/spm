# venueService seam: the venue list used to decide transfer days (SCRUM-10,
# SCRUM-13), modelled on deps.get_current_user (same httpx.get style so tests
# stub one seam).
from typing import TYPE_CHECKING

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.availability import Venue
from app.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Sequence


def fetch_venues(authorization: str) -> "Sequence[Venue]":
    """Every venue's id, name and building from venueService
    ``GET /venues/locations`` (SCRUM-13 D11), called with the caller's token.

    Closed venues are included on purpose: they still locate where a
    catalogue row is based. A 403 here means venueService's permission on
    that route regressed; tests/test_venue_contract.py catches that.
    """
    try:
        base = str(get_settings().venue_service_url).rstrip("/")
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Service is not configured"
        ) from error
    try:
        response = httpx.get(
            f"{base}/venues/locations",
            headers={"Authorization": authorization},
            timeout=10,
        )
    except httpx.HTTPError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Venue service unavailable"
        ) from error
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if not response.is_success:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Venue service unavailable"
        )
    try:
        return [
            Venue(id=str(v["id"]), name=v["name"], location=v["location"])
            for v in response.json()
        ]
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Venue service unavailable"
        ) from error
