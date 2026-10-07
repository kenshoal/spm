"""SCRUM-15 AC4: the requesting Coordinator is notified of a saved decision.

Case IDs match docs/testcases/scrum_15_testcases.md.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app import booking_decision_store
from app.booking_models import BookingRequest
from app.booking_notifications import BookingNotifier, get_booking_notifier
from app.booking_repository import booking_repository
from app.main import app

client = TestClient(app)
STAFF = "00000000-0000-0000-0000-000000000001"


class RecordingNotifier(BookingNotifier):
    def __init__(self) -> None:
        super().__init__(None)
        self.sent: list[dict] = []

    def send(self, event: dict) -> None:
        self.sent.append(event)


@pytest.fixture
def notifier():
    booking_decision_store.memory_decision_store.clear()
    recorder = RecordingNotifier()
    app.dependency_overrides[get_booking_notifier] = lambda: recorder
    yield recorder
    booking_decision_store.memory_decision_store.clear()


def make_request(slots=("AM",), venue_changes=None) -> BookingRequest:
    response = client.post(
        "/venues", json={"name": "Riverside Hall", "location": "Campus", "max_capacity": 50}
    )
    venue_id = response.json()["id"]
    if venue_changes:
        client.patch(f"/venues/{venue_id}", json=venue_changes)
    return booking_repository.create(
        BookingRequest(
            venue_id=venue_id,
            requested_by=str(uuid4()),
            event_request_id=str(uuid4()),
            event_name="Open day",
            start_date=date(2026, 10, 20),
            end_date=date(2026, 10, 21),
            slots=list(slots),
        )
    )


# AC4-H1 (happy): an approval notifies the requesting Coordinator once with the booking details
def test_approval_notifies_the_requesting_coordinator(notifier):
    booking = make_request()

    assert client.post(f"/booking-requests/{booking.id}/decision", json={"decision": "approved"}).status_code == 200

    assert notifier.sent == [
        {
            "event_type": "venue_booking_approved",
            "recipient_id": booking.requested_by,
            "event_id": f"booking-decision:{booking.id}",
            "payload": {
                "booking_request_id": booking.id,
                "event_request_id": booking.event_request_id,
                "event_name": "Open day",
                "venue_id": booking.venue_id,
                "venue_name": "Riverside Hall",
                "start_date": "2026-10-20",
                "end_date": "2026-10-21",
                "slots": ["AM"],
                "decision_reason": None,
                "suggested_alternative": None,
                "decided_by": STAFF,
            },
        }
    ]


# AC4-H2 (happy): a rejection notifies the requesting Coordinator with the reason and alternative
def test_rejection_notifies_with_reason_and_alternative(notifier):
    booking = make_request()

    response = client.post(
        f"/booking-requests/{booking.id}/decision",
        json={"decision": "rejected", "reason": "Hall under repair", "suggested_alternative": "Try Orchard Studio"},
    )

    assert response.status_code == 200
    [event] = notifier.sent
    assert event["event_type"] == "venue_booking_rejected"
    assert event["recipient_id"] == booking.requested_by
    assert event["payload"]["decision_reason"] == "Hall under repair"
    assert event["payload"]["suggested_alternative"] == "Try Orchard Studio"


# AC4-N1 (negative): refused, repeated, invalid or forbidden decisions send nothing
def test_no_notification_without_a_saved_decision(notifier):
    refused = make_request(venue_changes={"status": "blocked"})
    assert client.post(f"/booking-requests/{refused.id}/decision", json={"decision": "approved"}).status_code == 409

    decided = make_request()
    assert client.post(f"/booking-requests/{decided.id}/decision", json={"decision": "approved"}).status_code == 200
    notifier.sent.clear()
    assert client.post(f"/booking-requests/{decided.id}/decision", json={"decision": "rejected", "reason": "x"}).status_code == 409

    invalid = make_request()
    assert client.post(f"/booking-requests/{invalid.id}/decision", json={"decision": "rejected"}).status_code == 422

    assert notifier.sent == []


# AC4-N2 (negative): a notification failure never undoes or fails the decision
def test_notification_failure_does_not_undo_the_decision(monkeypatch):
    booking_decision_store.memory_decision_store.clear()

    def unreachable(*args, **kwargs):
        raise httpx.ConnectError("notification service down")

    monkeypatch.setattr("app.booking_notifications.httpx.post", unreachable)
    app.dependency_overrides[get_booking_notifier] = lambda: BookingNotifier("http://notifications.invalid/events")
    booking = make_request()

    response = client.post(f"/booking-requests/{booking.id}/decision", json={"decision": "approved"})

    assert response.status_code == 200
    assert booking_repository.get(booking.id).status.value == "approved"


# AC4-N3 (negative): without a configured receiver nothing is sent
def test_unconfigured_notifier_sends_nothing(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("no request expected without NOTIFICATION_SERVICE_URL")

    monkeypatch.setattr("app.booking_notifications.httpx.post", unexpected)
    BookingNotifier(None).send({"event_type": "venue_booking_approved", "recipient_id": "x", "payload": {}})


# AC4-H3 (happy): a configured notifier POSTs the event to the receiver with a timeout
def test_configured_notifier_posts_the_event(monkeypatch):
    calls = []

    def record(url, json, timeout):
        calls.append((url, json, timeout))
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.booking_notifications.httpx.post", record)
    event = {"event_type": "venue_booking_approved", "recipient_id": "x", "payload": {}}

    BookingNotifier("http://notification-service:8000/notifications/events").send(event)

    assert calls == [("http://notification-service:8000/notifications/events", event, 5)]


# AC4-N4 (negative): a receiver error is logged, not raised
def test_receiver_error_is_logged_not_raised(monkeypatch, caplog):
    def reject(url, json, timeout):
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.booking_notifications.httpx.post", reject)

    BookingNotifier("http://notification-service:8000/notifications/events").send(
        {"event_type": "venue_booking_approved", "recipient_id": "coord-1", "payload": {"booking_request_id": "b1"}}
    )

    assert "Failed to notify" in caplog.text
