from typing import Any, Protocol

import httpx

from app.config import Settings


class EventRequestRepository(Protocol):
    def list_arrangement_reviews(
        self, event_request_id: str
    ) -> list[dict[str, Any]]: ...

    def list_arrangement_reviews_for_arrangement(
        self, arrangement: str
    ) -> list[dict[str, Any]]: ...

    def clear_arrangement_review(
        self, review_id: str, actor_id: str, allowed_arrangements: list[str]
    ) -> dict[str, Any]: ...

    def list_status_history(self, event_request_id: str) -> list[dict[str, Any]]: ...

    def create(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def list_for_organiser(
        self, organiser_id: str
    ) -> list[dict[str, Any]]: ...

    def list_by_status(self, status: str) -> list[dict[str, Any]]: ...

    def get_organisation_id(self, user_id: str) -> str | None: ...

    def list_shared_with_organisation(
        self, organisation_id: str
    ) -> list[dict[str, Any]]: ...

    def get_for_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> dict[str, Any] | None: ...

    def get_by_id(self, event_request_id: str) -> dict[str, Any] | None: ...

    def get_by_ids(
        self, event_request_ids: list[str]
    ) -> list[dict[str, Any]]: ...

    def update_status(
        self, event_request_id: str, from_status: str, to_status: str
    ) -> dict[str, Any] | None: ...

    def advance_by_coordinator(
        self, event_request_id: str, coordinator_id: str, to_status: str
    ) -> dict[str, Any]: ...

    def decide_by_coordinator(
        self,
        event_request_id: str,
        coordinator_id: str,
        decision: str,
        reason: str | None,
    ) -> dict[str, Any]: ...

    def list_review_decisions(
        self, event_request_id: str
    ) -> list[dict[str, Any]]: ...

    def respond_to_clarification(
        self, event_request_id: str, organiser_id: str, response: str
    ) -> dict[str, Any]: ...

    def resume_review_by_coordinator(
        self, event_request_id: str, coordinator_id: str
    ) -> dict[str, Any]: ...

    def create_change_request(
        self, event_request_id: str, organiser_id: str, explanation: str,
        proposed_changes: dict[str, Any]
    ) -> dict[str, Any]: ...

    def list_change_requests(self, event_request_id: str) -> list[dict[str, Any]]: ...

    def decide_safety_review(
        self, event_request_id: str, officer_id: str, decision: str,
        reason: str | None, targets: list[dict[str, Any]]
    ) -> dict[str, Any]: ...

    def list_safety_reviews(self, event_request_id: str) -> list[dict[str, Any]]: ...

    def latest_coordinator_id(self, event_request_id: str) -> str | None: ...

    def decide_change_request(
        self, event_request_id: str, change_request_id: str,
        coordinator_id: str, decision: str, reason: str | None
    ) -> dict[str, Any]: ...

    def update_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None: ...

    def submit_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None: ...

    def delete_for_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> bool: ...


class SupabaseRepositoryError(RuntimeError):
    """Raised when the Supabase Data API cannot complete an operation."""


class EventRequestRpcError(SupabaseRepositoryError):
    """The transition RPC was rejected by the database function.

    errcode carries the Postgres ERRCODE the function raised (P0002 not
    found, P0003 not the assigned coordinator, P0004 transition not
    allowed, P0005 not ready for safety review) so callers can map failures
    without parsing message text. details is the DETAIL the function set, if
    any: for P0005, the outstanding items as a JSON array.
    """

    def __init__(
        self,
        message: str,
        errcode: str | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message)
        self.errcode = errcode
        self.details = details


class SupabaseEventRequestRepository:
    """Persists organiser drafts through Supabase's Data API."""

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

    def list_arrangement_reviews(
        self, event_request_id: str
    ) -> list[dict[str, Any]]:
        """Use the shared outstanding predicate without changing HTTP visibility."""
        return self._request_table(
            "POST",
            "/rpc/get_outstanding_arrangement_reviews",
            json={"p_event_request_id": event_request_id},
        )

    def list_arrangement_reviews_for_arrangement(
        self, arrangement: str
    ) -> list[dict[str, Any]]:
        """Return raw domain-scoped evidence; outstanding/order belong to service."""
        return self._request_table(
            "GET", "/arrangement_reviews",
            params={"arrangement": f"eq.{arrangement}", "select": "*"},
        )

    def clear_arrangement_review(
        self, review_id: str, actor_id: str, allowed_arrangements: list[str]
    ) -> dict[str, Any]:
        """Only the exact-ID server RPC may write review audit fields."""
        try:
            response = self._client.post(
                "/rpc/clear_arrangement_review",
                json={
                    "p_review_id": review_id,
                    "p_actor_id": actor_id,
                    "p_allowed_arrangements": allowed_arrangements,
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise self._rpc_rejection(error.response) from error
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError("Arrangement reviews unavailable") from error
        return response.json()

    def list_status_history(self, event_request_id: str) -> list[dict[str, Any]]:
        """The controller checks SCRUM-39 visibility before this server-only read."""
        return self._request_table(
            "GET", "/event_request_status_history",
            params={
                "event_request_id": f"eq.{event_request_id}",
                "order": "occurred_at.asc,id.asc", "select": "*",
            },
        )

    def list_for_organiser(
        self, organiser_id: str
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            params={
                "organiser_id": f"eq.{organiser_id}",
                "order": "created_at.desc",
                "select": "*",
            },
        )

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            params={
                "status": f"eq.{status}",
                "order": "created_at.desc",
                "select": "*",
            },
        )

    def get_organisation_id(self, user_id: str) -> str | None:
        rows = self._request_table(
            "GET",
            "/organisation_members",
            params={
                "user_id": f"eq.{user_id}",
                "select": "organisation_id",
                "limit": "1",
            },
        )
        return rows[0]["organisation_id"] if rows else None

    def list_shared_with_organisation(
        self, organisation_id: str
    ) -> list[dict[str, Any]]:
        """Non-Draft requests recorded against one client organisation."""
        return self._request(
            "GET",
            params={
                "organisation_id": f"eq.{organisation_id}",
                "status": "neq.Draft",
                "order": "created_at.desc",
                "select": "*",
            },
        )

    def get_for_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            params={
                "id": f"eq.{event_request_id}",
                "organiser_id": f"eq.{organiser_id}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_by_id(self, event_request_id: str) -> dict[str, Any] | None:
        """Look up a request for an authorised coordination workflow."""
        rows = self._request(
            "GET",
            params={
                "id": f"eq.{event_request_id}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_by_ids(self, event_request_ids: list[str]) -> list[dict[str, Any]]:
        if not event_request_ids:
            return []
        return self._request(
            "GET",
            params={
                "id": f"in.({','.join(event_request_ids)})",
                "order": "created_at.desc",
                "select": "*",
            },
        )

    def update_status(
        self, event_request_id: str, from_status: str, to_status: str
    ) -> dict[str, Any] | None:
        """Scoped to from_status, like every other write here is scoped to
        an expected current state — a concurrent transition away from
        from_status makes this a no-op (returns None) rather than clobbering
        whatever the row became."""
        rows = self._request(
            "PATCH",
            json={"status": to_status},
            params={
                "id": f"eq.{event_request_id}",
                "status": f"eq.{from_status}",
                "select": "*",
            },
            headers={"Prefer": "return=representation"},
        )
        return rows[0] if rows else None

    def advance_by_coordinator(
        self, event_request_id: str, coordinator_id: str, to_status: str
    ) -> dict[str, Any]:
        try:
            response = self._client.post(
                "/rpc/advance_event_request_by_coordinator",
                json={
                    "p_event_request_id": event_request_id,
                    "p_coordinator_id": coordinator_id,
                    "p_to_status": to_status,
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise self._rpc_rejection(error.response) from error
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the event request operation"
            ) from error
        return response.json()

    def decide_by_coordinator(
        self,
        event_request_id: str,
        coordinator_id: str,
        decision: str,
        reason: str | None,
    ) -> dict[str, Any]:
        """Persist the review decision and status through one database RPC."""
        try:
            response = self._client.post(
                "/rpc/decide_event_request_by_coordinator",
                json={
                    "p_event_request_id": event_request_id,
                    "p_coordinator_id": coordinator_id,
                    "p_decision_status": decision,
                    "p_reason": reason,
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise self._rpc_rejection(error.response) from error
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the event request operation"
            ) from error
        return response.json()

    def list_review_decisions(
        self, event_request_id: str
    ) -> list[dict[str, Any]]:
        return self._request_table(
            "GET",
            "/event_request_review_decisions",
            params={
                "event_request_id": f"eq.{event_request_id}",
                "order": "decided_at.desc,id.desc",
                "select": "*",
            },
        )

    def create_change_request(
        self,
        event_request_id: str,
        organiser_id: str,
        explanation: str,
        proposed_changes: dict[str, Any],
    ) -> dict[str, Any]:
        return self._call_rpc(
            "create_event_change_request",
            {
                "p_event_request_id": event_request_id,
                "p_organiser_id": organiser_id,
                "p_explanation": explanation,
                "p_proposed_changes": proposed_changes,
            },
        )

    def list_change_requests(self, event_request_id: str) -> list[dict[str, Any]]:
        return self._request_table(
            "GET",
            "/event_change_requests",
            params={
                "event_request_id": f"eq.{event_request_id}",
                "order": "created_at.desc",
                "select": "*",
            },
        )

    def decide_change_request(
        self,
        event_request_id: str,
        change_request_id: str,
        coordinator_id: str,
        decision: str,
        reason: str | None,
    ) -> dict[str, Any]:
        return self._call_rpc(
            "decide_event_change_request",
            {
                "p_event_request_id": event_request_id,
                "p_change_request_id": change_request_id,
                "p_coordinator_id": coordinator_id,
                "p_decision": decision,
                "p_reason": reason,
            },
        )

    def decide_safety_review(
        self,
        event_request_id: str,
        officer_id: str,
        decision: str,
        reason: str | None,
        targets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._call_rpc(
            "decide_safety_review",
            {
                "p_event_request_id": event_request_id,
                "p_officer_id": officer_id,
                "p_decision": decision,
                "p_reason": reason,
                "p_targets": targets,
            },
        )

    def list_safety_reviews(self, event_request_id: str) -> list[dict[str, Any]]:
        return self._request_table(
            "GET",
            "/safety_reviews",
            params={
                "event_request_id": f"eq.{event_request_id}",
                "order": "decided_at.desc,id.desc",
                "select": "*",
            },
        )

    def latest_coordinator_id(self, event_request_id: str) -> str | None:
        rows = self._request_table(
            "GET",
            "/event_coordinator_assignments",
            params={
                "event_request_id": f"eq.{event_request_id}",
                "order": "id.desc",
                "limit": "1",
                "select": "coordinator_id",
            },
        )
        return rows[0]["coordinator_id"] if rows else None

    def _call_rpc(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                f"/rpc/{name}",
                json=payload,
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise self._rpc_rejection(error.response) from error
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the event request operation"
            ) from error
        return response.json()

    def respond_to_clarification(
        self, event_request_id: str, organiser_id: str, response: str
    ) -> dict[str, Any]:
        """Attach one organiser response to the latest clarification request."""
        try:
            result = self._client.post(
                "/rpc/respond_to_event_request_clarification",
                json={
                    "p_event_request_id": event_request_id,
                    "p_organiser_id": organiser_id,
                    "p_response": response,
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
            result.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise self._rpc_rejection(error.response) from error
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the event request operation"
            ) from error
        return result.json()

    def resume_review_by_coordinator(
        self, event_request_id: str, coordinator_id: str
    ) -> dict[str, Any]:
        """Resume a returned review only after the organiser has responded."""
        try:
            result = self._client.post(
                "/rpc/resume_event_request_review_by_coordinator",
                json={
                    "p_event_request_id": event_request_id,
                    "p_coordinator_id": coordinator_id,
                },
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
            result.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise self._rpc_rejection(error.response) from error
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the event request operation"
            ) from error
        return result.json()

    @staticmethod
    def _rpc_rejection(response: httpx.Response) -> EventRequestRpcError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        return EventRequestRpcError(
            "Supabase rejected the coordinator status transition",
            errcode=body.get("code"),
            details=body.get("details"),
        )

    def update_for_organiser(
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
                "organiser_id": f"eq.{organiser_id}",
                "status": "eq.Draft",
                "select": "*",
            },
            headers={"Prefer": "return=representation"},
        )
        return rows[0] if rows else None

    def submit_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = self._request(
            "PATCH",
            json={**values, "status": "Submitted"},
            params={
                "id": f"eq.{event_request_id}",
                "organiser_id": f"eq.{organiser_id}",
                "status": "eq.Draft",
                "select": "*",
            },
            headers={"Prefer": "return=representation"},
        )
        return rows[0] if rows else None

    def delete_for_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> bool:
        rows = self._request(
            "DELETE",
            params={
                "id": f"eq.{event_request_id}",
                "organiser_id": f"eq.{organiser_id}",
                "status": "eq.Draft",
                "select": "id",
            },
            headers={"Prefer": "return=representation"},
        )
        return bool(rows)

    def _request(self, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        return self._request_table(method, "/event_requests", **kwargs)

    def _request_table(
        self, method: str, path: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the event request operation"
            ) from error
        return response.json()

    def close(self) -> None:
        self._client.close()
