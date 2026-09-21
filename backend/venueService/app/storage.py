"""Storage interfaces and request-scoped database resources."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Protocol

import httpx
from fastapi import Depends

from app.block_models import VenueBlock, VenueBlockCreate
from app.block_repository import block_repository
from app.config import Settings, get_settings
from app.models import Venue, VenueCreate, VenueUpdate
from app.repository import repository


class VenueStore(Protocol):
    def create(self, data: VenueCreate) -> Venue: ...
    def get(self, venue_id: str) -> Venue | None: ...
    def list(self) -> list[Venue]: ...
    def update(self, venue_id: str, data: VenueUpdate) -> Venue | None: ...


class BlockStore(Protocol):
    def create(
        self, venue_id: str, data: VenueBlockCreate, created_by: str
    ) -> VenueBlock: ...
    def get(self, block_id: str) -> VenueBlock | None: ...
    def list(self) -> list[VenueBlock]: ...
    def list_for_venue(self, venue_id: str) -> list[VenueBlock]: ...


@dataclass
class Stores:
    venues: VenueStore
    blocks: BlockStore


def get_stores(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[Stores]:
    if settings.venue_storage_backend == "memory":
        yield Stores(repository, block_repository)
        return

    from app.supabase_repository import (
        SupabaseBlockRepository,
        SupabaseDataAPI,
        SupabaseVenueRepository,
    )

    # Shared by the two repository dependencies during one request, then closed.
    with httpx.Client(timeout=10) as client:
        api = SupabaseDataAPI(
            client,
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )
        yield Stores(SupabaseVenueRepository(api), SupabaseBlockRepository(api))
