import httpx
import pytest

from app.services.notification_client import NotificationClient


# Purpose: No Notification System exists yet — unconfigured must never attempt a call.
def test_noop_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("httpx.post should not be called when unconfigured")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    NotificationClient(None).notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )


# Purpose: Confirms the payload shape matches the original NotificationOutbox design.
def test_posts_expected_payload_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient("https://notifications.example.com/events").notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )

    assert captured["url"] == "https://notifications.example.com/events"
    assert captured["json"] == {
        "event_type": "coordinator_assigned",
        "recipient_id": "coord-1",
        "payload": {
            "event_request_id": "req-1",
            "coordinator_id": "coord-1",
            "assigned_by": "ops-1",
        },
    }


# Purpose: A network failure must be logged, never raised — it can't be allowed
# to fail the assignment it's reporting on.
def test_connection_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient("https://notifications.example.com/events").notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )


# Purpose: A non-2xx response must also be swallowed, not just a connection failure.
def test_error_response_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://notifications.example.com/events"
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: httpx.Response(
            500, json={"error": "boom"}, request=httpx.Request("POST", url)
        ),
    )

    NotificationClient("https://notifications.example.com/events").notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )
