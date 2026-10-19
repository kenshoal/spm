"""Native delivery progress and current-recipient facts for committed reviews."""

from typing import Any, Protocol

import httpx

from app.config import Settings
from app.repositories.event_request_repository import SupabaseRepositoryError


class ArrangementReviewNotificationRepository(Protocol):
    def list_pending(self, *, limit: int) -> list[dict[str, Any]]: ...
    def begin_attempt(self, review_id: str) -> dict[str, Any] | None: ...
    def record_accepted(self, review_id: str, recipient_id: str) -> None: ...
    def complete_if_resolved(self, review_id: str) -> bool: ...


class SupabaseArrangementReviewNotificationRepository:
    def __init__(
        self,
        supabase_url: str,
        secret_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"apikey": secret_key}
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
    ) -> "SupabaseArrangementReviewNotificationRepository":
        return cls(
            str(settings.supabase_url), settings.supabase_secret_key.get_secret_value()
        )

    def list_pending(self, *, limit: int) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "/arrangement_review_notification_outbox",
            params={
                "published_at": "is.null",
                "order": "last_attempted_at.asc.nullsfirst,occurred_at.asc,review_id.asc",
                "limit": str(limit),
                "select": "review_id",
            },
        ).json()

    def begin_attempt(self, review_id: str) -> dict[str, Any] | None:
        return self._request(
            "POST",
            "/rpc/begin_arrangement_review_notification_attempt",
            json={"p_review_id": review_id},
        ).json()

    def record_accepted(self, review_id: str, recipient_id: str) -> None:
        self._request(
            "POST",
            "/rpc/record_arrangement_review_notification_accepted",
            json={
                "p_review_id": review_id,
                "p_recipient_id": recipient_id,
            },
        )

    def complete_if_resolved(self, review_id: str) -> bool:
        return (
            self._request(
                "POST",
                "/rpc/complete_arrangement_review_notification",
                json={"p_review_id": review_id},
            ).json()
            is True
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Arrangement notification delivery store unavailable"
            ) from error
        return response

    def close(self) -> None:
        self._client.close()
