"""SCRUM-38 AC4: registered Attendees are told when their event is cancelled or its
dates change. Case IDs match docs/testcases/scrum_38_testcases.md.
"""

from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from test_event_change_date_plan import NEW, OLD
from test_event_change_request import eligible_fixture
from test_event_transition_controller import headers

from app.services.event_transition_service import EventTransitionService
from app.services.notification_client import NotificationClient

NOTIFICATIONS_URL = "https://notifications.example.com/events"
ATTENDEES = ["attendee-1", "attendee-2"]


class SpyNotificationClient:
    """Records Attendee notices; the other notices are ignored."""

    def __init__(self) -> None:
        self.cancelled: list[dict[str, Any]] = []
        self.changed: list[dict[str, Any]] = []

    def notify_event_cancelled(self, **kwargs: Any) -> None:
        self.cancelled.append(kwargs)

    def notify_event_changed(self, **kwargs: Any) -> None:
        self.changed.append(kwargs)

    def notify_event_change_approved(self, **kwargs: Any) -> None:
        pass

    def notify_event_change_rejected(self, **kwargs: Any) -> None:
        pass


def with_spy(client: Any, spy: Any) -> None:
    state = client.app.state
    state.event_request_service.notification_client = spy
    state.event_transition_service = EventTransitionService(
        state.event_request_service, spy
    )


def cancel(client: Any, event_id: str, caller: str = "coord-1"):
    return client.post(
        f"/event-requests/{event_id}/cancellation", headers=headers(caller)
    )


# AC4-H1 (happy): Cancelling an event tells every registered Attendee, once the
# cancellation is saved.
def test_cancelling_notifies_the_registered_attendees() -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    events.registered_attendees[event_id] = list(ATTENDEES)
    spy = SpyNotificationClient()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert events.rows[event_id]["status"] == "Cancelled"
    assert spy.cancelled == [
        {
            "event_request_id": event_id,
            "event_name": events.rows[event_id]["event_name"],
            "attendee_ids": ATTENDEES,
        }
    ]


# AC4-P1 (partition): An event nobody registered for sends nothing.
def test_cancelling_with_no_attendees_sends_nothing() -> None:
    client, _, event_id = eligible_fixture("Planning")
    spy = SpyNotificationClient()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert spy.cancelled == []


@pytest.mark.parametrize(
    ("status", "caller", "expected"),
    [("Completed", "coord-1", 409), ("Confirmed", "coord-2", 403)],
    ids=["AC4-N1a", "AC4-N1b"],
)
# AC4-N1 (negative): A refused cancellation (terminal status, not the assigned
# Coordinator) leaves the event alone and tells nobody.
def test_refused_cancellation_notifies_nobody(
    status: str, caller: str, expected: int
) -> None:
    client, events, event_id = eligible_fixture(status)
    events.registered_attendees[event_id] = list(ATTENDEES)
    spy = SpyNotificationClient()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id, caller)

    assert response.status_code == expected
    assert events.rows[event_id]["status"] == status
    assert spy.cancelled == []


# AC4-N2 (negative): If the Attendees cannot be listed, the cancellation still stands
# and nothing is sent.
def test_attendee_lookup_failure_does_not_block_cancellation() -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    events.registered_attendees[event_id] = list(ATTENDEES)
    events.attendee_lookup_fails = True
    spy = SpyNotificationClient()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert events.rows[event_id]["status"] == "Cancelled"
    assert spy.cancelled == []


def approve_dates(client: Any, events: Any, event_id: str, monkeypatch: Any, changes: dict):
    """Approve a pending change through the real route; the repository's prepared
    approval stands in for the database function (as in the SCRUM-35 date tests)."""
    created = client.post(
        f"/event-requests/{event_id}/change-requests",
        headers=headers("organiser-1"),
        json={"explanation": "Move the agreed activity.", **changes},
    )
    assert created.status_code == 201, created.text
    pending = created.json()
    saved = {
        **pending,
        "status": "Approved",
        "coordinator_id": "coord-1",
        "decision_reason": None,
        "decided_at": "2026-10-22T12:00:00Z",
        "applied_booking_plan": [],
    }
    monkeypatch.setattr(
        events, "approve_date_change_request", lambda *a: deepcopy(saved), raising=False
    )
    monkeypatch.setattr(
        events, "decide_change_request", lambda *a: deepcopy(saved)
    )
    response = client.post(
        f"/event-requests/{event_id}/change-requests/{pending['id']}/decision",
        headers=headers("coord-1"),
        json={"decision": "Approved"},
    )
    return pending, response


# AC4-H2 (happy): An approved date change tells every registered Attendee the new
# dates, once the approval is saved.
def test_approved_date_change_notifies_the_registered_attendees(monkeypatch) -> None:
    client, events, event_id = eligible_fixture("Planning")
    events.rows[event_id]["proposed_date_times"] = deepcopy(OLD)
    events.registered_attendees[event_id] = list(ATTENDEES)
    spy = SpyNotificationClient()
    with_spy(client, spy)

    with client:
        pending, response = approve_dates(
            client, events, event_id, monkeypatch, {"proposed_date_times": NEW}
        )

    assert response.status_code == 200, response.text
    assert spy.changed == [
        {
            "event_request_id": event_id,
            "event_name": events.rows[event_id]["event_name"],
            "change_request_id": pending["id"],
            "proposed_date_times": pending["proposed_changes"]["proposed_date_times"],
            "attendee_ids": ATTENDEES,
        }
    ]


# AC4-P2 (partition): An approved change that Attendees cannot see (attendance, venue,
# equipment) tells them nothing.
def test_approved_change_to_hidden_fields_notifies_no_attendee(monkeypatch) -> None:
    client, events, event_id = eligible_fixture("Planning")
    events.registered_attendees[event_id] = list(ATTENDEES)
    spy = SpyNotificationClient()
    with_spy(client, spy)

    with client:
        _, response = approve_dates(
            client, events, event_id, monkeypatch, {"expected_attendance": 80}
        )

    assert response.status_code == 200, response.text
    assert spy.changed == []


# AC4-N3 (negative): A rejected change tells no Attendee.
def test_rejected_change_notifies_no_attendee() -> None:
    client, events, event_id = eligible_fixture("Planning")
    events.registered_attendees[event_id] = list(ATTENDEES)
    spy = SpyNotificationClient()
    with_spy(client, spy)

    with client:
        created = client.post(
            f"/event-requests/{event_id}/change-requests",
            headers=headers("organiser-1"),
            json={"explanation": "Move it.", "proposed_date_times": NEW},
        )
        response = client.post(
            f"/event-requests/{event_id}/change-requests/{created.json()['id']}/decision",
            headers=headers("coord-1"),
            json={"decision": "Rejected", "reason": "Not possible."},
        )

    assert response.status_code == 200, response.text
    assert spy.changed == []


# AC4-N4 (negative): An unreachable notification service never blocks a cancellation.
def test_notification_outage_does_not_block_cancellation(monkeypatch) -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    events.registered_attendees[event_id] = list(ATTENDEES)
    with_spy(client, NotificationClient(NOTIFICATIONS_URL))

    def unreachable(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", unreachable)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert events.rows[event_id]["status"] == "Cancelled"


# AC4-H3 (happy): The client sends one cancellation notice per Attendee, each with
# its own stable key.
def test_cancelled_notice_posts_one_notice_per_attendee(monkeypatch) -> None:
    posted: list[dict] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        posted.append(kwargs["json"])  # type: ignore[arg-type]
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_event_cancelled(
        event_request_id="event-1", event_name="Dinner", attendee_ids=ATTENDEES
    )

    assert posted == [
        {
            "event_type": "event_cancelled",
            "recipient_id": attendee,
            "event_id": str(uuid5(NAMESPACE_URL, f"event-cancelled:event-1:{attendee}")),
            "payload": {"event_request_id": "event-1", "event_name": "Dinner"},
        }
        for attendee in ATTENDEES
    ]


# AC4-H4 (happy): The client sends the new dates to each Attendee, keyed by the change.
def test_changed_notice_carries_the_new_dates(monkeypatch) -> None:
    posted: list[dict] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        posted.append(kwargs["json"])  # type: ignore[arg-type]
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_event_changed(
        event_request_id="event-1",
        event_name="Dinner",
        change_request_id="change-1",
        proposed_date_times=["2026-11-22T11:00:00+08:00"],
        attendee_ids=["attendee-1"],
    )

    assert posted == [
        {
            "event_type": "event_changed",
            "recipient_id": "attendee-1",
            "event_id": str(uuid5(NAMESPACE_URL, "event-changed:change-1:attendee-1")),
            "payload": {
                "event_request_id": "event-1",
                "event_name": "Dinner",
                "change_request_id": "change-1",
                "proposed_date_times": ["2026-11-22T11:00:00+08:00"],
            },
        }
    ]


# AC4-N5 (negative): One Attendee's failed notice does not stop the others.
def test_one_failed_notice_does_not_stop_the_rest(monkeypatch, caplog) -> None:
    attempts: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        recipient = kwargs["json"]["recipient_id"]  # type: ignore[index]
        attempts.append(recipient)
        if recipient == "attendee-1":
            raise httpx.ConnectError("connection refused")
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_event_cancelled(
        event_request_id="event-1", event_name="Dinner", attendee_ids=ATTENDEES
    )

    assert attempts == ATTENDEES
    assert "Failed to notify attendee-1" in caplog.text
