from typing import Any, Protocol

import httpx

from app.config import Settings


class EventRequestRepository(Protocol):
    def create(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def list_for_temporary_organiser(
        self, organiser_id: str
    ) -> list[dict[str, Any]]: ...

    def get_for_temporary_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> dict[str, Any] | None: ...

    def update_for_temporary_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None: ...

    def delete_for_temporary_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> bool: ...


class SupabaseRepositoryError(RuntimeError):
    """Raised when the Supabase Data API cannot complete an operation."""


class SupabaseEventRequestRepository:
    """Persists temporary-organiser drafts through Supabase's Data API."""

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
    def from_settings(cls, settings: Settings) -> "SupabaseEventRequestRepository":
        return cls(
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        rows = self._request(
            "POST",
            json=values,
            params={"select": "*"},
            headers={"Prefer": "return=representation"},
        )
        return rows[0]

    def list_for_temporary_organiser(
        self, organiser_id: str
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            params={
                "temporary_organiser_id": f"eq.{organiser_id}",
                "order": "created_at.desc",
                "select": "*",
            },
        )

    def get_for_temporary_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            params={
                "id": f"eq.{event_request_id}",
                "temporary_organiser_id": f"eq.{organiser_id}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def update_for_temporary_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = self._request(
            "PATCH",
            json=values,
            params={
                "id": f"eq.{event_request_id}",
                "temporary_organiser_id": f"eq.{organiser_id}",
                "status": "eq.Draft",
                "select": "*",
            },
            headers={"Prefer": "return=representation"},
        )
        return rows[0] if rows else None

    def delete_for_temporary_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> bool:
        rows = self._request(
            "DELETE",
            params={
                "id": f"eq.{event_request_id}",
                "temporary_organiser_id": f"eq.{organiser_id}",
                "status": "eq.Draft",
                "select": "id",
            },
            headers={"Prefer": "return=representation"},
        )
        return bool(rows)

    def _request(self, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            response = self._client.request(method, "/event_requests", **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the event request operation"
            ) from error
        return response.json()

    def close(self) -> None:
        self._client.close()
