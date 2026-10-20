"""Technical support requirement and assignment persistence (SCRUM-19).

Writes go through the `record_technical_support_requirement` and
`assign_technical_support_staff` database functions, which re-check the
coordinator, status, requirement and suitability under the event row lock;
reads are plain table selects.
"""

from typing import Any, Protocol

import httpx

from app.config import Settings
from app.repositories.event_request_repository import SupabaseRepositoryError


class TechnicalSupportRpcError(SupabaseRepositoryError):
    """A technical support database function refused the call.

    errcode is the Postgres ERRCODE (P0002 not found, P0003 not the assigned
    coordinator, P0004 status refuses support work, P0005 staff not suitable,
    23505 duplicate assignment) and reason the function's message ('event
    request not found', 'technical support requirement not found', ...), so
    callers never parse prose written for people.
    """

    def __init__(
        self, message: str, errcode: str | None = None, reason: str | None = None
    ) -> None:
        super().__init__(message)
        self.errcode = errcode
        self.reason = reason


class TechnicalSupportRepository(Protocol):
    def record_requirement(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def assign(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def get_requirement(self, requirement_id: str) -> dict[str, Any] | None: ...

    def list_requirements(self, event_request_id: str) -> list[dict[str, Any]]: ...

    def list_assignments(self, event_request_id: str) -> list[dict[str, Any]]: ...

    def list_candidates(self, requirement_id: str) -> list[dict[str, Any]]: ...


class SupabaseTechnicalSupportRepository:
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
    ) -> "SupabaseTechnicalSupportRepository":
        return cls(
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )

    def record_requirement(self, values: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                "/rpc/record_technical_support_requirement",
                json={
                    "p_event_request_id": values["event_request_id"],
                    "p_coordinator_id": values["coordinator_id"],
                    "p_description": values["description"],
                    "p_skill_tag": values["skill_tag"],
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the technical support operation"
            ) from error
        if response.status_code >= 500:
            raise SupabaseRepositoryError(
                "Supabase could not complete the technical support operation"
            )
        if response.is_error:
            raise self._refusal(response)
        return response.json()

    def assign(self, values: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                "/rpc/assign_technical_support_staff",
                json={
                    "p_event_request_id": values["event_request_id"],
                    "p_requirement_id": values["requirement_id"],
                    "p_staff_id": values["staff_id"],
                    "p_coordinator_id": values["coordinator_id"],
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the technical support operation"
            ) from error
        if response.status_code >= 500:
            raise SupabaseRepositoryError(
                "Supabase could not complete the technical support operation"
            )
        if response.is_error:
            raise self._refusal(response)
        return response.json()

    def get_requirement(self, requirement_id: str) -> dict[str, Any] | None:
        rows = self._get(
            "/technical_support_requirements",
            {"select": "*", "id": f"eq.{requirement_id}", "limit": "1"},
        )
        return rows[0] if rows else None

    def list_requirements(self, event_request_id: str) -> list[dict[str, Any]]:
        return self._get(
            "/technical_support_requirements",
            {
                "select": "*",
                "event_request_id": f"eq.{event_request_id}",
                "order": "recorded_at.asc,id.asc",
            },
        )

    def list_assignments(self, event_request_id: str) -> list[dict[str, Any]]:
        return self._get(
            "/technical_support_assignments",
            {
                "select": "*",
                "event_request_id": f"eq.{event_request_id}",
                "order": "assigned_at.asc,id.asc",
            },
        )

    def list_candidates(self, requirement_id: str) -> list[dict[str, Any]]:
        try:
            response = self._client.post(
                "/rpc/list_technical_support_candidates",
                json={"p_requirement_id": requirement_id},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the technical support operation"
            ) from error
        return response.json()

    @staticmethod
    def _refusal(response: httpx.Response) -> TechnicalSupportRpcError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        return TechnicalSupportRpcError(
            "Supabase rejected the technical support request",
            errcode=body.get("code"),
            reason=body.get("message"),
        )

    def _get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the technical support operation"
            ) from error
        return response.json()

    def close(self) -> None:
        self._client.close()
