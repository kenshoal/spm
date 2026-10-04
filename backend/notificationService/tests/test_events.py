from pathlib import Path
from typing import Any

import pytest
from fakes import FakeNotificationRepository, make_client
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

ENDPOINT = "/notifications/events"


# Purpose: The contract must accept, unchanged, the body eventRequestService's
# NotificationClient.notify_coordinator_assigned already sends (SCRUM-14/37),
# and store it for that coordinator.
def test_stores_the_existing_coordinator_assigned_hook_body() -> None:
    repository = FakeNotificationRepository()
    payload = {
        "event_request_id": "11111111-1111-4111-8111-111111111111",
        "coordinator_id": "coord-1",
        "assigned_by": "ops-1",
    }
    with make_client(repository) as client:
        response = client.post(
            ENDPOINT,
            json={
                "event_type": "coordinator_assigned",
                "recipient_id": "coord-1",
                "payload": payload,
            },
        )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert [
        (row["recipient_id"], row["event_type"], row["payload"])
        for row in repository.rows
    ] == [("coord-1", "coordinator_assigned", payload)]


# Purpose: The log line is how a caller confirms its hook reached this service.
def test_logs_each_accepted_event(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level("INFO", logger="app.main"),
        make_client(FakeNotificationRepository()) as client,
    ):
        client.post(
            ENDPOINT,
            json={"event_type": "event.cancelled", "recipient_id": "organiser-1"},
        )

    assert "Received event.cancelled event for recipient organiser-1" in caplog.text


# Purpose: A retried event (same event_id, same recipient) must never notify
# twice, and the retry must still succeed so the caller stops retrying.
def test_a_repeated_event_is_stored_once(caplog: pytest.LogCaptureFixture) -> None:
    repository = FakeNotificationRepository()
    event = {
        "event_id": "22222222-2222-4222-8222-222222222222",
        "event_type": "event_request.submitted",
        "recipient_id": "organiser-1",
    }
    with (
        caplog.at_level("INFO", logger="app.main"),
        make_client(repository) as client,
    ):
        first = client.post(ENDPOINT, json=event)
        retry = client.post(ENDPOINT, json=event)

    assert (first.status_code, retry.status_code) == (202, 202)
    assert len(repository.rows) == 1
    assert "duplicate" in caplog.text


# Purpose: One workflow event may notify several people (e.g. a cancellation
# reaches both Organiser and Coordinator) under the same event_id.
def test_the_same_event_id_can_notify_different_recipients() -> None:
    repository = FakeNotificationRepository()
    with make_client(repository) as client:
        for recipient in ("organiser-1", "coord-1"):
            client.post(
                ENDPOINT,
                json={
                    "event_id": "evt-1",
                    "event_type": "event.cancelled",
                    "recipient_id": recipient,
                },
            )

    assert sorted(row["recipient_id"] for row in repository.rows) == [
        "coord-1",
        "organiser-1",
    ]


# Purpose: Without an event_id nothing identifies a retry, so each event is new.
def test_events_without_an_event_id_are_all_stored() -> None:
    repository = FakeNotificationRepository()
    event = {"event_type": "event.cancelled", "recipient_id": "organiser-1"}
    with make_client(repository) as client:
        client.post(ENDPOINT, json=event)
        client.post(ENDPOINT, json=event)

    assert len(repository.rows) == 2


# Purpose: A hook with nothing extra to say may omit the payload entirely.
def test_payload_defaults_to_empty() -> None:
    repository = FakeNotificationRepository()
    with make_client(repository) as client:
        response = client.post(
            ENDPOINT,
            json={"event_type": "event.cancelled", "recipient_id": "organiser-1"},
        )

    assert response.status_code == 202
    assert repository.rows[0]["payload"] == {}


# Purpose: Malformed events are refused at the boundary so callers find
# contract mistakes during development, not as silently lost notifications.
@pytest.mark.parametrize(
    "body",
    [
        {"recipient_id": "coord-1", "payload": {}},
        {"event_type": "coordinator_assigned", "payload": {}},
        {"event_type": "  ", "recipient_id": "coord-1"},
        {"event_type": "coordinator_assigned", "recipient_id": ""},
        {"event_type": "coordinator_assigned", "recipient_id": "x" * 65},
        {"event_type": "coordinator_assigned", "recipient_id": "c", "payload": []},
    ],
)
def test_rejects_malformed_events(body: dict[str, Any]) -> None:
    repository = FakeNotificationRepository()
    with make_client(repository) as client:
        response = client.post(ENDPOINT, json=body)

    assert response.status_code == 422
    assert repository.rows == []


# Purpose: A database outage is reported as 502 so the caller logs a warning
# (callers never let this break the action that caused the event).
def test_reports_a_store_failure_as_bad_gateway() -> None:
    repository = FakeNotificationRepository()
    repository.fail = True
    with make_client(repository) as client:
        response = client.post(
            ENDPOINT, json={"event_type": "event.cancelled", "recipient_id": "o-1"}
        )

    assert response.status_code == 502


# Purpose: Without Supabase settings the service says so instead of crashing.
def test_reports_missing_supabase_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no stray .env file can configure it
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                ENDPOINT, json={"event_type": "event.cancelled", "recipient_id": "o-1"}
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
