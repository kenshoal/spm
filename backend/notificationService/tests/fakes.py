from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import Header
from fastapi.testclient import TestClient

from app.auth import get_current_user_id
from app.delivery import Delivery
from app.main import create_app
from app.repository import NotificationStoreError

START = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)


class FakeNotificationRepository:
    """In-memory stand-in with the same (recipient_id, event_id) uniqueness."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.fail = False

    def save(
        self,
        *,
        event_type: str,
        recipient_id: str,
        payload: dict[str, Any],
        event_id: str | None,
        in_inbox: bool = True,
    ) -> bool:
        self._maybe_fail()
        if event_id is not None and any(
            row["recipient_id"] == recipient_id and row["event_id"] == event_id
            for row in self.rows
        ):
            return False
        self.rows.append(
            {
                "id": str(uuid4()),
                "recipient_id": recipient_id,
                "event_type": event_type,
                "payload": payload,
                "event_id": event_id,
                "in_inbox": in_inbox,
                "read_at": None,
                # Strictly increasing, so "newest first" is deterministic.
                "created_at": (START + timedelta(minutes=len(self.rows))).isoformat(),
            }
        )
        return True

    def list_for_recipient(
        self, recipient_id: str, *, unread_only: bool, limit: int
    ) -> list[dict[str, Any]]:
        self._maybe_fail()
        rows = [
            row
            for row in self.rows
            if row["recipient_id"] == recipient_id
            and row["in_inbox"]
            and not (unread_only and row["read_at"])
        ]
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)[:limit]

    def mark_read(
        self, notification_id: str, recipient_id: str
    ) -> dict[str, Any] | None:
        self._maybe_fail()
        for row in self.rows:
            if row["id"] == notification_id and row["recipient_id"] == recipient_id:
                row["read_at"] = row["read_at"] or datetime.now(UTC).isoformat()
                return row
        return None

    def _maybe_fail(self) -> None:
        if self.fail:
            raise NotificationStoreError("Supabase is down")


class FakeChannelSettings:
    """Channel per event type; a type with no entry is in-app only."""

    def __init__(self, channels: dict[str, str] | None = None) -> None:
        self.channels = channels or {}
        self.fail = False

    def channel_for(self, event_type: str) -> str:
        if self.fail:
            raise RuntimeError("settings store is down")
        return self.channels.get(event_type, "in_app")


class FakeAddressBook:
    def __init__(self, addresses: dict[str, str] | None = None) -> None:
        self.addresses = addresses or {}

    def email_for(self, recipient_id: str) -> str | None:
        return self.addresses.get(recipient_id)


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail = False

    def send(self, *, to: str, subject: str, body: str) -> None:
        if self.fail:
            raise ConnectionRefusedError("mail server is down")
        self.sent.append({"to": to, "subject": subject, "body": body})


def make_client(
    repository: FakeNotificationRepository, delivery: Delivery | None = None
) -> TestClient:
    """A client whose bearer token is taken as the caller's user id."""
    app = create_app(repository, delivery)

    def fake_user_id(authorization: str = Header()) -> str:
        return authorization.removeprefix("Bearer ")

    app.dependency_overrides[get_current_user_id] = fake_user_id
    return TestClient(app)


def signed_in_as(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}
