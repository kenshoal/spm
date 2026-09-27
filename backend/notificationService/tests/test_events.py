from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ENDPOINT = "/notifications/events"


# Purpose: The contract must accept, unchanged, the body eventRequestService's
# NotificationClient.notify_coordinator_assigned already sends (SCRUM-14/37).
def test_accepts_the_existing_coordinator_assigned_hook_body() -> None:
    response = client.post(
        ENDPOINT,
        json={
            "event_type": "coordinator_assigned",
            "recipient_id": "coord-1",
            "payload": {
                "event_request_id": "11111111-1111-4111-8111-111111111111",
                "coordinator_id": "coord-1",
                "assigned_by": "ops-1",
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


# Purpose: Until delivery exists, the log line is how a caller confirms its hook
# reached this service, so every accepted event must be logged.
def test_logs_each_accepted_event(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="app.main"):
        client.post(
            ENDPOINT,
            json={"event_type": "event.cancelled", "recipient_id": "organiser-1"},
        )

    assert "Received event.cancelled event for recipient organiser-1" in caplog.text


# Purpose: An idempotency key (e.g. the outbox event UUID SCRUM-11 requires) is
# part of the contract, so callers can send it before delivery is built.
def test_accepts_an_optional_event_id() -> None:
    response = client.post(
        ENDPOINT,
        json={
            "event_id": "22222222-2222-4222-8222-222222222222",
            "event_type": "event_request.submitted",
            "recipient_id": "organiser-1",
            "payload": {},
        },
    )

    assert response.status_code == 202


# Purpose: A hook with nothing extra to say may omit the payload entirely.
def test_payload_defaults_to_empty() -> None:
    response = client.post(
        ENDPOINT,
        json={"event_type": "event.cancelled", "recipient_id": "organiser-1"},
    )

    assert response.status_code == 202


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
    response = client.post(ENDPOINT, json=body)

    assert response.status_code == 422
