"""Venue stores and storage selection.

The routers depend on the ``VenueStore`` interface, not on a storage
mechanism. ``VENUE_STORAGE_BACKEND`` selects the implementation:

* ``memory`` (default) — ``VenueRepository`` below; used by unit tests and
  standalone development. Data is lost when the process stops.
* ``supabase`` — ``SupabaseVenueRepository``, persisting to ``public.venues``.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.models import Venue, VenueCreate, VenueUpdate, _now


class VenueStore(Protocol):
    def create(self, data: VenueCreate) -> Venue: ...
    def get(self, venue_id: str) -> Venue | None: ...
    def list(self) -> list[Venue]: ...
    def update(self, venue_id: str, data: VenueUpdate) -> Venue | None: ...
    def update_timing(
        self,
        venue_id: str,
        setup_minutes: int | None,
        turnaround_minutes: int | None,
        changed_by: str,
    ) -> Venue | None: ...


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
        # Strictly after the previous value: Windows clock ticks can repeat _now().
        updated_at = max(_now(), venue.updated_at + timedelta(microseconds=1))
        updated = venue.model_copy(update={**patch, "updated_at": updated_at})
        self._venues[venue.id] = updated
        return updated

    def update_timing(
        self,
        venue_id: str,
        setup_minutes: int | None,
        turnaround_minutes: int | None,
        changed_by: str,
    ) -> Venue | None:
        # Review flags live in the database (0055); this store only keeps the times.
        del changed_by
        times = {"setup_minutes": setup_minutes, "turnaround_minutes": turnaround_minutes}
        return self.update(
            venue_id, VenueUpdate(**{k: v for k, v in times.items() if v is not None})
        )

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
