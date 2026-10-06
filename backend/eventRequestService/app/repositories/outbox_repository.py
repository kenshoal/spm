from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.repositories.event_request_repository import SupabaseRepositoryError


class OutboxRepository(Protocol):
    def list_unpublished(self, *, limit: int) -> list[dict[str, Any]]: ...

    def mark_published(self, outbox_id: str) -> None: ...


class SupabaseOutboxRepository:
    """Reads and marks submission events in public.event_request_outbox.

    Rows are written by the database triggers in migration 0008, never by this
    service; it only relays them. `published_at` stays null until the event has
    been delivered, which is what makes an undelivered event retryable.
    """

    def __init__(
        self,
        supabase_url: str,
        secret_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"apikey": secret_key}
        # Legacy service-role keys are JWTs; new sb_secret keys use apikey only.
        if not secret_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {secret_key}"
        self._client = httpx.Client(
            base_url=f"{supabase_url.rstrip('/')}/rest/v1",
            headers=headers,
            timeout=10,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupabaseOutboxRepository":
        return cls(
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )

    def list_unpublished(self, *, limit: int) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            params={
                "published_at": "is.null",
                "order": "occurred_at.asc,id.asc",
                "limit": str(limit),
                "select": "*",
            },
        )
        return response.json()

    def mark_published(self, outbox_id: str) -> None:
        # Only an unpublished row is updated, so the first delivery time is kept.
        self._request(
            "PATCH",
            params={"id": f"eq.{outbox_id}", "published_at": "is.null"},
            json={"published_at": datetime.now(UTC).isoformat()},
        )

    def _request(self, method: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, "/event_request_outbox", **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the outbox operation"
            ) from error
        return response

    def close(self) -> None:
        self._client.close()
