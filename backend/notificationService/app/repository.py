from datetime import UTC, datetime
from typing import Any, Protocol

import httpx2

from app.config import Settings


class NotificationStoreError(RuntimeError):
    """Supabase could not complete a notification read or write."""


class NotificationRepository(Protocol):
    def save(
        self,
        *,
        event_type: str,
        recipient_id: str,
        payload: dict[str, Any],
        event_id: str | None,
        in_inbox: bool = True,
    ) -> bool: ...

    def list_for_recipient(
        self, recipient_id: str, *, unread_only: bool, limit: int
    ) -> list[dict[str, Any]]: ...

    def mark_read(
        self, notification_id: str, recipient_id: str
    ) -> dict[str, Any] | None: ...


class SupabaseNotificationRepository:
    """Stores notifications in public.notifications through Supabase's Data API.

    The unique (recipient_id, event_id) constraint from migration 0017 is what
    makes delivery idempotent: a repeated event is ignored by the database, so
    a retried hook can never notify the same person twice.
    """

    def __init__(
        self,
        supabase_url: str,
        secret_key: str,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        headers = {"apikey": secret_key}
        # Legacy service-role keys are JWTs; new sb_secret keys use apikey only.
        if not secret_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {secret_key}"
        self._client = httpx2.Client(
            base_url=f"{supabase_url.rstrip('/')}/rest/v1",
            headers=headers,
            timeout=10,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupabaseNotificationRepository":
        return cls(
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )

    def save(
        self,
        *,
        event_type: str,
        recipient_id: str,
        payload: dict[str, Any],
        event_id: str | None,
        in_inbox: bool = True,
    ) -> bool:
        rows = self._request(
            "POST",
            params={"on_conflict": "recipient_id,event_id"},
            headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
            json={
                "event_type": event_type,
                "recipient_id": recipient_id,
                "payload": payload,
                "event_id": event_id,
                "in_inbox": in_inbox,
            },
        )
        # An ignored duplicate comes back as an empty list.
        return bool(rows)

    def list_for_recipient(
        self, recipient_id: str, *, unread_only: bool, limit: int
    ) -> list[dict[str, Any]]:
        params = {
            "recipient_id": f"eq.{recipient_id}",
            # An email-only notification is stored, to guard against repeats,
            # but is not part of the inbox.
            "in_inbox": "eq.true",
            "order": "created_at.desc,id.desc",
            "limit": str(limit),
            "select": "*",
        }
        if unread_only:
            params["read_at"] = "is.null"
        return self._request("GET", params=params)

    def mark_read(
        self, notification_id: str, recipient_id: str
    ) -> dict[str, Any] | None:
        owned = {"id": f"eq.{notification_id}", "recipient_id": f"eq.{recipient_id}"}
        # Only an unread row is updated, so the first read time is kept.
        updated = self._request(
            "PATCH",
            params={**owned, "read_at": "is.null"},
            headers={"Prefer": "return=representation"},
            json={"read_at": datetime.now(UTC).isoformat()},
        )
        if updated:
            return updated[0]
        existing = self._request("GET", params={**owned, "select": "*"})
        return existing[0] if existing else None

    def _request(self, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            response = self._client.request(method, "/notifications", **kwargs)
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise NotificationStoreError(
                "Supabase could not complete the notification operation"
            ) from error
        return response.json()

    def close(self) -> None:
        self._client.close()
