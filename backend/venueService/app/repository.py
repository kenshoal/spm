"""Venue stores and storage selection.

The routers depend on the ``VenueStore`` interface, not on a storage
mechanism. ``VENUE_STORAGE_BACKEND`` selects the implementation:

* ``memory`` (default) — ``VenueRepository`` below; used by unit tests and
  standalone development. Data is lost when the process stops.
* ``supabase`` — ``SupabaseVenueRepository``, persisting to ``public.venues``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.models import Venue, VenueCreate, VenueUpdate, _now


class VenueStore(Protocol):
    def create(self, data: VenueCreate) -> Venue: ...
    def get(self, venue_id: str) -> Venue | None: ...
    def list(self) -> list[Venue]: ...
    def update(self, venue_id: str, data: VenueUpdate) -> Venue | None: ...


class VenueRepository:
    """In-memory venue store."""

    def __init__(self) -> None:
        self._venues: dict[str, Venue] = {}

    def create(self, data: VenueCreate) -> Venue:
        venue = Venue(**data.model_dump())
        self._venues[venue.id] = venue
        return venue

    def get(self, venue_id: str) -> Venue | None:
        return self._venues.get(venue_id)

    def list(self) -> list[Venue]:
        return list(self._venues.values())

    def update(self, venue_id: str, data: VenueUpdate) -> Venue | None:
        venue = self._venues.get(venue_id)
        if venue is None:
            return None
        patch = data.model_dump(exclude_unset=True)
        updated = venue.model_copy(update={**patch, "updated_at": _now()})
        self._venues[venue.id] = updated
        return updated

    def clear(self) -> None:
        self._venues.clear()


# Module-level singleton used when VENUE_STORAGE_BACKEND=memory.
repository = VenueRepository()


@lru_cache
def _supabase_repository() -> VenueStore:
    from app.supabase_repository import SupabaseVenueRepository

    settings = get_settings()
    return SupabaseVenueRepository(
        str(settings.supabase_url),
        settings.supabase_secret_key.get_secret_value(),
    )


def get_repository() -> VenueStore:
    """FastAPI dependency returning the configured venue store."""

    if get_settings().venue_storage_backend == "supabase":
        return _supabase_repository()
    return repository
