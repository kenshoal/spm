from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_event_review_decision import under_review_fixture
from test_event_transition_controller import headers

from app.services.event_transition_service import EventTransitionService
from app.services.notification_client import NotificationClient

NOTIFICATIONS_URL = "https://notifications.example.com/events"
CLARIFICATION = "Please clarify the accessibility plan."


class SpyNotificationClient:
    """Records clarification notices without sending anything."""

    def __init__(self) -> None:
        self.clarifications: list[dict[str, Any]] = []

    def notify_clarification_requested(self, **kwargs: Any) -> None:
        self.clarifications.append(kwargs)

    # Approved and Rejected notices are SCRUM-36's; they are ignored here.
    def notify_event_request_approved(self, **kwargs: Any) -> None:
        pass

    def notify_event_request_rejected(self, **kwargs: Any) -> None:
        pass


def notify_through(client: TestClient, notifications: Any) -> None:
    """Rebuild the app's transition service around the given notification client."""
    state = client.app.state
    state.event_transition_service = EventTransitionService(
        state.event_request_service, notifications
    )


def decide(client: TestClient, event_request_id: str, caller: str, body: dict) -> Any:
    with client:
        return client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers(caller),
            json=body,
        )


# AC3-H1 (happy): Requesting clarification tells the Organiser who owns the request
# what the Coordinator needs to know, once the decision has been recorded.
def test_requesting_clarification_notifies_the_organiser() -> None:
    client, events, event_request_id = under_review_fixture()
    spy = SpyNotificationClient()
    notify_through(client, spy)

    response = decide(
        client,
        event_request_id,
        "coord-1",
        {"decision": "Changes Requested", "reason": CLARIFICATION},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "Changes Requested"
    assert spy.clarifications == [
        {
            "event_request_id": event_request_id,
            "organiser_id": events.rows[event_request_id]["organiser_id"],
            "reason": CLARIFICATION,
        }
    ]


@pytest.mark.parametrize(
    ("decision", "reason"),
    [
        ("Approved", None),
        ("Rejected", "The proposed event is outside the programme scope."),
    ],
    ids=["AC3-P1", "AC3-P2"],
)
# AC3-P1, AC3-P2 (partition): Only a clarification request sends a clarification
# notice. Telling an Organiser to clarify an approved or rejected request would be
# wrong; approval and rejection notices belong to SCRUM-36.
def test_other_outcomes_send_no_clarification_notice(
    decision: str, reason: str | None
) -> None:
    client, events, event_request_id = under_review_fixture()
    spy = SpyNotificationClient()
    notify_through(client, spy)

    response = decide(
        client, event_request_id, "coord-1", {"decision": decision, "reason": reason}
    )

    assert response.status_code == 200
    assert events.rows[event_request_id]["status"] == decision
    assert spy.clarifications == []


@pytest.mark.parametrize(
    ("caller", "stored_status", "reason", "expected_status"),
    [
        ("coord-2", "Under Review", CLARIFICATION, 403),
        ("coord-1", "Approved", CLARIFICATION, 409),
        ("coord-1", "Under Review", "   ", 422),
    ],
    ids=["AC3-N1", "AC3-N2", "AC3-N3"],
)
# AC3-N1, AC3-N2, AC3-N3 (negative): A refused decision (not the assigned Coordinator,
# not under review, no reason given) leaves the request unchanged and tells nobody
# to clarify something that was never recorded.
def test_refused_decision_sends_no_clarification_notice(
    caller: str, stored_status: str, reason: str, expected_status: int
) -> None:
    client, events, event_request_id = under_review_fixture()
    events.rows[event_request_id]["status"] = stored_status
    spy = SpyNotificationClient()
    notify_through(client, spy)

    response = decide(
        client,
        event_request_id,
        caller,
        {"decision": "Changes Requested", "reason": reason},
    )

    assert response.status_code == expected_status
    assert events.rows[event_request_id]["status"] == stored_status
    assert events.review_decision_rows == []
    assert spy.clarifications == []


# AC3-N4 (negative): An unreachable notification service never blocks the Coordinator:
# the decision and its reason are still recorded, and the Organiser can read the
# clarification on the request itself.
def test_notification_outage_does_not_block_the_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, events, event_request_id = under_review_fixture()
    notify_through(client, NotificationClient(NOTIFICATIONS_URL))

    def unreachable(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", unreachable)

    response = decide(
        client,
        event_request_id,
        "coord-1",
        {"decision": "Changes Requested", "reason": CLARIFICATION},
    )

    assert response.status_code == 200
    assert events.rows[event_request_id]["status"] == "Changes Requested"
    assert [row["reason"] for row in events.review_decision_rows] == [CLARIFICATION]


# AC3-H2 (happy): The notice is addressed to the Organiser and carries the
# clarification required, in the body notificationService's contract expects.
def test_clarification_posts_notice_to_the_organiser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            202, json={"status": "accepted"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_clarification_requested(
        event_request_id="req-1", organiser_id="org-1", reason=CLARIFICATION
    )

    assert captured["url"] == NOTIFICATIONS_URL
    assert captured["json"] == {
        "event_type": "clarification_requested",
        "recipient_id": "org-1",
        "payload": {"event_request_id": "req-1", "reason": CLARIFICATION},
    }


@pytest.mark.parametrize(
    "outcome",
    [httpx.ConnectError("connection refused"), 500],
    ids=["AC3-N5", "AC3-N6"],
)
# AC3-N5, AC3-N6 (negative): A network failure or an error response is logged, never
# raised, so a notification problem cannot fail the decision it reports on.
def test_clarification_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: object,
) -> None:
    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(
            outcome, request=httpx.Request("POST", NOTIFICATIONS_URL)
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_clarification_requested(
        event_request_id="req-1", organiser_id="org-1", reason=CLARIFICATION
    )

    assert "Failed to notify organiser org-1" in caplog.text


# AC3-N7 (negative): With no notification service configured nothing is attempted.
def test_clarification_is_a_no_op_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("httpx.post should not be called when unconfigured")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    NotificationClient(None).notify_clarification_requested(
        event_request_id="req-1", organiser_id="org-1", reason=CLARIFICATION
    )
