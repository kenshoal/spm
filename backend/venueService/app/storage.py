"""Block storage interface and request-scoped database resources.

Venue storage is selected by ``app.repository``; this module selects where
venue blocks are stored using the same ``VENUE_STORAGE_BACKEND`` setting.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Protocol

import httpx
from fastapi import Depends

from app.block_models import VenueBlock, VenueBlockCreate
from app.block_repository import block_repository
from app.config import Settings, get_settings


class BlockStore(Protocol):
    def create(
        self, venue_id: str, data: VenueBlockCreate, created_by: str
    ) -> VenueBlock: ...
    def get(self, block_id: str) -> VenueBlock | None: ...
    def list(self) -> list[VenueBlock]: ...
    def list_for_venue(self, venue_id: str) -> list[VenueBlock]: ...


def get_block_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[BlockStore]:
    if settings.venue_storage_backend == "memory":
        yield block_repository
        return

    from app.supabase_block_repository import (
        SupabaseBlockRepository,
        SupabaseDataAPI,
    )

    # Used for the duration of one request, then closed.
    with httpx.Client(timeout=10) as client:
        api = SupabaseDataAPI(
            client,
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )
        yield SupabaseBlockRepository(api)
