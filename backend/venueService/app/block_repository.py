"""Temporary in-memory block storage, following the venue repository pattern."""

from app.block_models import VenueBlock, VenueBlockCreate


class VenueBlockRepository:
    def __init__(self) -> None:
        self._blocks: dict[str, VenueBlock] = {}

    def create(
        self, venue_id: str, data: VenueBlockCreate, created_by: str
    ) -> VenueBlock:
        block = VenueBlock(
            **data.model_dump(), venue_id=venue_id, created_by=created_by
        )
        self._blocks[block.id] = block
        return block

    def get(self, block_id: str) -> VenueBlock | None:
        return self._blocks.get(block_id)

    def list(self) -> list[VenueBlock]:
        return list(self._blocks.values())

    def clear(self) -> None:
        self._blocks.clear()


block_repository = VenueBlockRepository()
