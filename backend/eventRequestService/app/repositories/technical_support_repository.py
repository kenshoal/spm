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
        raise NotImplementedError

    @classmethod
    def from_settings(
        cls, settings: Settings
    ) -> "SupabaseTechnicalSupportRepository":
        raise NotImplementedError

    def record_requirement(self, values: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def assign(self, values: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def get_requirement(self, requirement_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_requirements(self, event_request_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_assignments(self, event_request_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_candidates(self, requirement_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
