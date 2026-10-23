from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from test_clarification_notification import decide, notify_through
from test_event_review_decision import under_review_fixture

from app.services.notification_client import NotificationClient

NOTIFICATIONS_URL = "https://notifications.example.com/events"
REJECTION = "The proposed event is outside the programme scope."


class SpyNotificationClient:
    """Records decision-outcome notices without sending anything."""

    def __init__(self) -> None:
        self.approved: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []
        self.clarifications: list[dict[str, Any]] = []

    def notify_event_request_approved(self, **kwargs: Any) -> None:
        self.approved.append(kwargs)

    def notify_event_request_rejected(self, **kwargs: Any) -> None:
        self.rejected.append(kwargs)

    def notify_clarification_requested(self, **kwargs: Any) -> None:
        self.clarifications.append(kwargs)


# AC1-H1 (happy): Approving a request tells the Organiser who owns it, once the
# decision has been recorded.
def test_approving_a_request_notifies_the_organiser() -> None:
    client, events, event_request_id = under_review_fixture()
    spy = SpyNotificationClient()
    notify_through(client, spy)

    response = decide(client, event_request_id, "coord-1", {"decision": "Approved"})

    assert response.status_code == 200
    assert response.json()["status"] == "Approved"
    assert spy.approved == [
        {
            "event_request_id": event_request_id,
            "organiser_id": events.rows[event_request_id]["organiser_id"],
        }
    ]
    assert spy.rejected == []


# AC1-H2 (happy): Rejecting a request tells the Organiser why, once the decision has
# been recorded.
def test_rejecting_a_request_notifies_the_organiser_with_the_reason() -> None:
    client, events, event_request_id = under_review_fixture()
    spy = SpyNotificationClient()
    notify_through(client, spy)

    response = decide(
        client,
        event_request_id,
        "coord-1",
        {"decision": "Rejected", "reason": REJECTION},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "Rejected"
    assert spy.rejected == [
        {
            "event_request_id": event_request_id,
            "organiser_id": events.rows[event_request_id]["organiser_id"],
            "reason": REJECTION,
        }
    ]
    assert spy.approved == []


# AC1-P1 (partition): Returning a request for clarification sends the clarification
# notice only, never an approved or rejected one.
def test_clarification_sends_no_approved_or_rejected_notice() -> None:
    client, _, event_request_id = under_review_fixture()
    spy = SpyNotificationClient()
    notify_through(client, spy)

    response = decide(
        client,
        event_request_id,
        "coord-1",
        {"decision": "Changes Requested", "reason": "Please clarify the plan."},
    )

    assert response.status_code == 200
    assert len(spy.clarifications) == 1
    assert spy.approved == []
    assert spy.rejected == []


# AC1-N1 (negative): A refused decision (not the assigned Coordinator, not under
# review, rejection with no reason) leaves the request unchanged and tells nobody.
@pytest.mark.parametrize(
    ("caller", "stored_status", "body", "expected_status"),
    [
        ("coord-2", "Under Review", {"decision": "Approved"}, 403),
        ("coord-1", "Approved", {"decision": "Approved"}, 409),
        ("coord-1", "Under Review", {"decision": "Rejected", "reason": "  "}, 422),
    ],
    ids=["AC1-N1a", "AC1-N1b", "AC1-N1c"],
)
def test_refused_decision_sends_no_outcome_notice(
    caller: str, stored_status: str, body: dict, expected_status: int
) -> None:
    client, events, event_request_id = under_review_fixture()
    events.rows[event_request_id]["status"] = stored_status
    spy = SpyNotificationClient()
    notify_through(client, spy)

    response = decide(client, event_request_id, caller, body)

    assert response.status_code == expected_status
    assert events.rows[event_request_id]["status"] == stored_status
    assert spy.approved == []
    assert spy.rejected == []


def capture_post(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            202, json={"status": "accepted"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


# AC1-H3 (happy): The approved notice goes to the Organiser in the body
# notificationService expects, with a stable key so a repeat is stored once.
def test_approved_notice_posts_the_agreed_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = capture_post(monkeypatch)

    NotificationClient(NOTIFICATIONS_URL).notify_event_request_approved(
        event_request_id="req-1", organiser_id="org-1"
    )

    assert captured["url"] == NOTIFICATIONS_URL
    assert captured["json"] == {
        "event_type": "event_request_approved",
        "recipient_id": "org-1",
        "event_id": str(uuid5(NAMESPACE_URL, "event-request-approved:req-1")),
        "payload": {"event_request_id": "req-1"},
    }


# AC1-H3 (happy): The rejected notice carries the reason the Coordinator gave.
def test_rejected_notice_posts_the_agreed_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = capture_post(monkeypatch)

    NotificationClient(NOTIFICATIONS_URL).notify_event_request_rejected(
        event_request_id="req-1", organiser_id="org-1", reason=REJECTION
    )

    assert captured["json"] == {
        "event_type": "event_request_rejected",
        "recipient_id": "org-1",
        "event_id": str(uuid5(NAMESPACE_URL, "event-request-rejected:req-1")),
        "payload": {"event_request_id": "req-1", "reason": REJECTION},
    }


def send_both(client: NotificationClient) -> None:
    client.notify_event_request_approved(event_request_id="req-1", organiser_id="org-1")
    client.notify_event_request_rejected(
        event_request_id="req-1", organiser_id="org-1", reason=REJECTION
    )


@pytest.mark.parametrize(
    "outcome",
    [httpx.ConnectError("connection refused"), 500],
    ids=["AC1-N3a", "AC1-N3b"],
)
# AC1-N3 (negative): A network failure or an error response is logged, never
# raised, so a notification problem cannot fail the decision it reports on.
def test_outcome_notice_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: object,
) -> None:
    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("POST", NOTIFICATIONS_URL))

    monkeypatch.setattr(httpx, "post", fake_post)

    send_both(NotificationClient(NOTIFICATIONS_URL))

    assert caplog.text.count("Failed to notify organiser org-1") == 2


# AC1-N4 (negative): With no notification service configured nothing is attempted.
def test_outcome_notice_is_a_no_op_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("httpx.post should not be called when unconfigured")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    send_both(NotificationClient(None))


# AC1-N2 (negative): An unreachable notification service never blocks the
# Coordinator: the decision is still recorded.
def test_notification_outage_does_not_block_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, events, event_request_id = under_review_fixture()
    notify_through(client, NotificationClient(NOTIFICATIONS_URL))

    def unreachable(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", unreachable)

    response = decide(client, event_request_id, "coord-1", {"decision": "Approved"})

    assert response.status_code == 200
    assert events.rows[event_request_id]["status"] == "Approved"
