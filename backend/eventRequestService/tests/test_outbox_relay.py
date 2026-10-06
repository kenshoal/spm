import asyncio
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.repositories import SupabaseRepositoryError
from app.services.outbox_relay import OutboxRelay, build_outbox_relay


def outbox_row(outbox_id: str, organiser_id: str) -> dict[str, Any]:
    return {
        "id": outbox_id,
        "event_request_id": f"req-for-{outbox_id}",
        "organiser_id": organiser_id,
        "event_type": "event_request.submitted",
        "payload": {
            "event_request_id": f"req-for-{outbox_id}",
            "organiser_id": organiser_id,
            "status": "Submitted",
        },
        "occurred_at": "2026-10-02T03:00:00+00:00",
        "published_at": None,
    }


class FakeOutboxRepository:
    def __init__(self, rows: list[dict[str, Any]], failing_lists: int = 0) -> None:
        self.rows = rows
        self.published: list[str] = []
        self._failing_lists = failing_lists

    def list_unpublished(self, *, limit: int) -> list[dict[str, Any]]:
        if self._failing_lists:
            self._failing_lists -= 1
            raise SupabaseRepositoryError("Supabase is down")
        return [row for row in self.rows if row["id"] not in self.published][:limit]

    def mark_published(self, outbox_id: str) -> None:
        self.published.append(outbox_id)


class FakeNotificationClient:
    def __init__(self, undeliverable: set[str] | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self._undeliverable = undeliverable or set()

    def notify_event_request_submitted(
        self, *, event_id: str, organiser_id: str, payload: dict[str, Any]
    ) -> bool:
        if event_id in self._undeliverable:
            return False
        self.sent.append(
            {"event_id": event_id, "organiser_id": organiser_id, "payload": payload}
        )
        return True


# AC1-H1 (happy): SCRUM-37 AC1 — every submitted request's Organiser gets a confirmation,
# and a delivered event is marked so it is not sent again on the next pass.
def test_relay_once_confirms_each_submission_to_its_organiser() -> None:
    repository = FakeOutboxRepository(
        [outbox_row("outbox-1", "org-a"), outbox_row("outbox-2", "org-b")]
    )
    client = FakeNotificationClient()

    delivered = OutboxRelay(repository, client).relay_once()

    assert delivered == 2
    assert client.sent == [
        {
            "event_id": "outbox-1",
            "organiser_id": "org-a",
            "payload": {
                "event_request_id": "req-for-outbox-1",
                "organiser_id": "org-a",
                "status": "Submitted",
            },
        },
        {
            "event_id": "outbox-2",
            "organiser_id": "org-b",
            "payload": {
                "event_request_id": "req-for-outbox-2",
                "organiser_id": "org-b",
                "status": "Submitted",
            },
        },
    ]
    assert repository.published == ["outbox-1", "outbox-2"]


# AC1-N1 (negative): An event that could not be delivered stays unpublished so the next pass
# retries it, and it does not hold back the events behind it.
def test_relay_once_leaves_undelivered_event_for_retry() -> None:
    repository = FakeOutboxRepository(
        [outbox_row("outbox-1", "org-a"), outbox_row("outbox-2", "org-b")]
    )
    client = FakeNotificationClient(undeliverable={"outbox-1"})

    delivered = OutboxRelay(repository, client).relay_once()

    assert delivered == 1
    assert [event["event_id"] for event in client.sent] == ["outbox-2"]
    assert repository.published == ["outbox-2"]


# AC1-N1 (negative): One failed pass (Supabase unreachable) must not stop the background
# relay; otherwise confirmations silently stop until the service restarts.
def test_run_forever_keeps_relaying_after_a_failed_pass() -> None:
    repository = FakeOutboxRepository(
        [outbox_row("outbox-1", "org-a")], failing_lists=1
    )
    client = FakeNotificationClient()
    relay = OutboxRelay(repository, client, interval_seconds=0)

    async def run_until_delivered() -> None:
        task = asyncio.create_task(relay.run_forever())
        for _ in range(200):
            if client.sent:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_until_delivered())

    assert repository.published == ["outbox-1"]


# AC1-H1 (happy): The relay runs for the lifetime of the app it is given to, so starting
# eventRequestService is all it takes for confirmations to flow.
def test_app_startup_runs_the_relay() -> None:
    repository = FakeOutboxRepository([outbox_row("outbox-1", "org-a")])
    client = FakeNotificationClient()
    relay = OutboxRelay(repository, client, interval_seconds=0)

    with TestClient(create_app(outbox_relay=relay)):
        deadline = time.monotonic() + 2
        while not repository.published and time.monotonic() < deadline:
            time.sleep(0.01)

    assert repository.published == ["outbox-1"]


# AC1-N2 (negative): Without notificationService configured there is nobody to deliver to,
# so no relay is built and outbox rows stay unpublished instead of being consumed.
def test_from_settings_is_none_without_notification_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.delenv("NOTIFICATION_SERVICE_URL", raising=False)

    assert OutboxRelay.from_settings(Settings(_env_file=None)) is None


# AC1-H2 (happy): With both Supabase and notificationService configured the relay is built.
def test_from_settings_builds_relay_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv(
        "NOTIFICATION_SERVICE_URL",
        "http://notification-service:8000/notifications/events",
    )

    assert isinstance(OutboxRelay.from_settings(Settings(_env_file=None)), OutboxRelay)


# AC1-N2 (negative): The relay is built when app.main is imported, so missing Supabase
# configuration must mean "no relay", never a service that fails to start.
def test_build_outbox_relay_is_none_without_supabase(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv(
        "NOTIFICATION_SERVICE_URL",
        "http://notification-service:8000/notifications/events",
    )
    get_settings.cache_clear()
    try:
        assert build_outbox_relay() is None
    finally:
        get_settings.cache_clear()
