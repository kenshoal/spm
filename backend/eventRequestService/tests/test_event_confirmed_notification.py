from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from test_safety_review import (
    COORDINATOR,
    REASON,
    TARGETS,
    decide,
    safety_fixture,
)

from app.services.event_transition_service import EventTransitionService
from app.services.notification_client import NotificationClient

NOTIFICATIONS_URL = "https://notifications.example.com/events"


class SpyNotificationClient:
    """Records safety-decision notices without sending anything."""

    def __init__(self) -> None:
        self.confirmed: list[dict[str, Any]] = []
        self.safety_changes: list[dict[str, Any]] = []

    def notify_event_confirmed(self, **kwargs: Any) -> None:
        self.confirmed.append(kwargs)

    def notify_safety_changes_requested(self, **kwargs: Any) -> None:
        self.safety_changes.append(kwargs)


def spy_on(client: Any) -> SpyNotificationClient:
    spy = SpyNotificationClient()
    state = client.app.state
    state.event_transition_service = EventTransitionService(
        state.event_request_service, spy
    )
    return spy


# AC3-H1 (happy): Safety approval confirms the event and tells its Organiser, once
# the decision has been recorded. The Coordinator gets no new notice.
def test_safety_approval_notifies_the_organiser_that_the_event_is_confirmed() -> None:
    client, events, event_request_id, _ = safety_fixture()
    spy = spy_on(client)

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 200
    assert events.rows[event_request_id]["status"] == "Confirmed"
    assert spy.confirmed == [
        {
            "event_request_id": event_request_id,
            "organiser_id": events.rows[event_request_id]["organiser_id"],
        }
    ]
    assert spy.safety_changes == []


# AC3-N1 (negative): Asking for changes returns the event to Planning, so nobody is
# told it is confirmed.
def test_safety_changes_requested_sends_no_confirmed_notice() -> None:
    client, _, event_request_id, _ = safety_fixture()
    spy = spy_on(client)

    response = decide(
        client,
        event_request_id,
        {"decision": "changes_requested", "reason": REASON, "targets": TARGETS},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "Planning"
    assert spy.confirmed == []
    assert len(spy.safety_changes) == 1


@pytest.mark.parametrize(
    "status", ["Planning", "Confirmed", "Approved"], ids=["AC3-N2a", "AC3-N2b", "AC3-N2c"]
)
# AC3-N2 (negative): An approval outside Safety Review, or a repeated one, is refused
# and tells nobody the event is confirmed.
def test_refused_approval_sends_no_confirmed_notice(status: str) -> None:
    client, events, event_request_id, _ = safety_fixture(status)
    spy = spy_on(client)

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 409
    assert events.rows[event_request_id]["status"] == status
    assert spy.confirmed == []


# AC3-N2 (negative): a non-officer cannot approve, so nobody is told.
def test_unauthorised_approval_sends_no_confirmed_notice() -> None:
    client, events, event_request_id, _ = safety_fixture()
    spy = spy_on(client)

    response = decide(client, event_request_id, {"decision": "approved"}, COORDINATOR)

    assert response.status_code == 403
    assert events.rows[event_request_id]["status"] == "Safety Review"
    assert spy.confirmed == []


# AC3-N3 (negative): An unreachable notification service never blocks confirmation.
def test_notification_outage_does_not_block_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, events, event_request_id, _ = safety_fixture()
    state = client.app.state
    state.event_transition_service = EventTransitionService(
        state.event_request_service, NotificationClient(NOTIFICATIONS_URL)
    )

    def unreachable(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", unreachable)

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 200
    assert events.rows[event_request_id]["status"] == "Confirmed"


# AC3-H2 (happy): The client posts the confirmed notice to the Organiser in the
# agreed shape, with a stable key so a repeat is stored once.
def test_confirmed_notice_posts_the_agreed_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_event_confirmed(
        event_request_id="req-1", organiser_id="org-1"
    )

    assert captured["url"] == NOTIFICATIONS_URL
    assert captured["json"] == {
        "event_type": "event_confirmed",
        "recipient_id": "org-1",
        "event_id": str(uuid5(NAMESPACE_URL, "event-confirmed:req-1")),
        "payload": {"event_request_id": "req-1"},
    }
