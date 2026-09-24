from typing import Any, Protocol

import httpx

from app.config import Settings
from app.repositories.event_request_repository import SupabaseRepositoryError


class CoordinatorAssignmentRpcError(SupabaseRepositoryError):
    """The atomic assignment function rejected the requested assignment."""

    def __init__(self, message: str, errcode: str | None = None) -> None:
        super().__init__(message)
        self.errcode = errcode


class CoordinatorAssignmentRepository(Protocol):
    def create(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def latest_for_event_request(
        self, event_request_id: str
    ) -> dict[str, Any] | None: ...

    def assigned_event_request_ids(self, event_request_ids: list[str]) -> set[str]: ...

    def list_for_coordinator(self, coordinator_id: str) -> list[dict[str, Any]]: ...

    def list_for_event_requests(
        self, event_request_ids: list[str]
    ) -> list[dict[str, Any]]: ...


class SupabaseCoordinatorAssignmentRepository:
    """Persists Coordinator assignments through Supabase's Data API.

    Every assignment is inserted as a new row rather than updating one in
    place, so `latest_for_event_request` — ordered by the autoincrementing
    `id`, not `assigned_at` (server-clock resolution isn't reliable enough to
    order two assignments made in quick succession) — is what "current
    assignment" means; the full history stays queryable.
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
    def from_settings(
        cls, settings: Settings
    ) -> "SupabaseCoordinatorAssignmentRepository":
        return cls(
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                "/rpc/assign_event_request_coordinator",
                json={
                    "p_event_request_id": values["event_request_id"],
                    "p_coordinator_id": values["coordinator_id"],
                    "p_assigned_by": values["assigned_by"],
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            try:
                errcode = error.response.json().get("code")
            except ValueError:
                errcode = None
            raise CoordinatorAssignmentRpcError(
                "Supabase rejected the coordinator assignment",
                errcode=errcode,
            ) from error
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the coordinator assignment operation"
            ) from error
        return response.json()

    def latest_for_event_request(
        self, event_request_id: str
    ) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            params={
                "event_request_id": f"eq.{event_request_id}",
                "order": "id.desc",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def assigned_event_request_ids(self, event_request_ids: list[str]) -> set[str]:
        if not event_request_ids:
            return set()
        rows = self._request(
            "GET",
            params={
                "event_request_id": f"in.({','.join(event_request_ids)})",
                "select": "event_request_id",
            },
        )
        return {row["event_request_id"] for row in rows}

    def list_for_coordinator(self, coordinator_id: str) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            params={
                "coordinator_id": f"eq.{coordinator_id}",
                "order": "id.asc",
                "select": "*",
            },
        )

    def list_for_event_requests(
        self, event_request_ids: list[str]
    ) -> list[dict[str, Any]]:
        if not event_request_ids:
            return []
        return self._request(
            "GET",
            params={
                "event_request_id": f"in.({','.join(event_request_ids)})",
                "select": "*",
            },
        )

    def _request(self, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            response = self._client.request(
                method, "/event_coordinator_assignments", **kwargs
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the coordinator assignment operation"
            ) from error
        return response.json()

    def close(self) -> None:
        self._client.close()
