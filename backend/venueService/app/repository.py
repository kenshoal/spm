"""In-memory venue store.

Scaffold only. The router depends on this interface, not on the storage
mechanism, so this can be swapped for a persistent backend (e.g. SQLAlchemy
against Postgres) once the project's database infrastructure lands.
"""

from __future__ import annotations

from app.models import Venue, VenueCreate, VenueUpdate, _now


class VenueRepository:
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


# Module-level singleton used by the default dependency wiring.
repository = VenueRepository()
