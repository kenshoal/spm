"""Venue block persistence through Supabase's Data API (``public.venue_blocks``).

Venues themselves are stored by ``app.supabase_repository``. The database owns
IDs/timestamps on insert. No schema changes or user creation are performed
here. Errors expose neither credentials nor raw database details.
"""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from app.block_models import VenueBlock, VenueBlockCreate

Model = TypeVar("Model", bound=BaseModel)


class StorageError(RuntimeError):
    def __init__(self, detail: str, status_code: int = 502) -> None:
        super().__init__(detail)
        self.status_code = status_code


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _decode(model: type[Model], row: dict) -> Model:
    try:
        return model.model_validate(row)
    except ValidationError:
        raise StorageError(
            "Stored data does not match the venue service schema"
        ) from None


class SupabaseDataAPI:
    def __init__(self, client: httpx.Client, url: str, secret_key: str) -> None:
        self.client = client
        self.url = url.rstrip("/") + "/rest/v1"
        self.headers = {"apikey": secret_key}
        if not secret_key.startswith("sb_secret_"):
            self.headers["Authorization"] = f"Bearer {secret_key}"

    def request(self, method: str, table: str, **kwargs: Any) -> list[dict]:
        headers = self.headers | kwargs.pop("headers", {})
        try:
            response = self.client.request(
                method, f"{self.url}/{table}", headers=headers, **kwargs
            )
        except httpx.HTTPError:
            raise StorageError("Database is unavailable") from None
        if not response.is_success:
            try:
                code = response.json().get("code")
            except (ValueError, AttributeError):
                code = None
            if code == "23503":
                raise StorageError("Referenced venue or creator no longer exists", 409)
            if code == "23505":
                raise StorageError("Database record already exists", 409)
            if code in {"23514", "23502", "22P02", "22001"}:
                raise StorageError("Request violates database field constraints", 422)
            raise StorageError("Database could not complete the operation")
        try:
            rows = response.json()
        except ValueError:
            raise StorageError("Database returned an invalid response") from None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise StorageError("Database returned an invalid response")
        return rows

    def list_rows(self, table: str, **filters: str) -> list[dict]:
        # Continue even after a short page: the project's row cap may be below
        # our requested limit. Otherwise later blocks could be silently missed.
        rows: list[dict] = []
        while True:
            page = self.request(
                "GET",
                table,
                params={
                    "select": "*",
                    "order": "id.asc",
                    "limit": "500",
                    "offset": str(len(rows)),
                    **filters,
                },
            )
            if not page:
                return rows
            rows.extend(page)

    def get_row(self, table: str, record_id: str) -> dict | None:
        if not _is_uuid(record_id):
            return None
        rows = self.request(
            "GET", table, params={"id": f"eq.{record_id}", "select": "*", "limit": "1"}
        )
        return rows[0] if rows else None

    def insert(self, table: str, payload: dict) -> dict:
        rows = self.request(
            "POST", table, json=payload, headers={"Prefer": "return=representation"}
        )
        if len(rows) != 1:
            raise StorageError("Database did not return the saved record")
        return rows[0]


class SupabaseBlockRepository:
    def __init__(self, api: SupabaseDataAPI) -> None:
        self.api = api

    def create(
        self, venue_id: str, data: VenueBlockCreate, created_by: str
    ) -> VenueBlock:
        if not _is_uuid(created_by):
            raise StorageError(
                "A real creator UUID is required for database storage", 503
            )
        values = data.model_dump(mode="json") | {
            "venue_id": venue_id,
            "created_by": created_by,
        }
        return _decode(VenueBlock, self.api.insert("venue_blocks", values))

    def get(self, block_id: str) -> VenueBlock | None:
        row = self.api.get_row("venue_blocks", block_id)
        return _decode(VenueBlock, row) if row is not None else None

    def list(self) -> list[VenueBlock]:
        return [_decode(VenueBlock, row) for row in self.api.list_rows("venue_blocks")]

    def list_for_venue(self, venue_id: str) -> list[VenueBlock]:
        if not _is_uuid(venue_id):
            return []
        return [
            _decode(VenueBlock, row)
            for row in self.api.list_rows("venue_blocks", venue_id=f"eq.{venue_id}")
        ]
