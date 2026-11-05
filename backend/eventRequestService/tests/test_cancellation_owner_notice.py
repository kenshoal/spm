"""SCRUM-57 AC1: the Organiser and the assigned Coordinator are told when an event is
cancelled. Case IDs match docs/testcases/scrum_57_testcases.md.
"""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from test_attendee_event_notification import (
    ATTENDEES,
    SpyNotificationClient,
    cancel,
    with_spy,
)
from test_event_change_request import eligible_fixture

from app.repositories.event_request_repository import SupabaseRepositoryError
from app.services.notification_client import NotificationClient

NOTIFICATIONS_URL = "https://notifications.example.com/events"


class OwnerSpy(SpyNotificationClient):
    """Also records the Organiser and Coordinator notices."""

    def __init__(self) -> None:
        super().__init__()
        self.recorded: list[dict[str, Any]] = []

    def notify_event_cancellation_recorded(self, **kwargs: Any) -> None:
        self.recorded.append(kwargs)


# AC1-H1 (happy): Cancelling tells the Organiser and the assigned Coordinator.
def test_cancelling_tells_the_organiser_and_the_coordinator() -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    spy = OwnerSpy()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert events.rows[event_id]["status"] == "Cancelled"
    assert spy.recorded == [
        {
            "event_request_id": event_id,
            "event_name": events.rows[event_id]["event_name"],
            "recipient_ids": ["organiser-1", "coord-1"],
        }
    ]


# AC1-H2 (happy): The client sends one notice per recipient, each with its own stable
# key.
def test_the_client_posts_one_notice_per_recipient(monkeypatch) -> None:
    posted: list[dict] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        posted.append(kwargs["json"])  # type: ignore[arg-type]
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_event_cancellation_recorded(
        event_request_id="event-1",
        event_name="Dinner",
        recipient_ids=["organiser-1", "coord-1"],
    )

    assert posted == [
        {
            "event_type": "event_cancellation_recorded",
            "recipient_id": recipient,
            "event_id": str(
                uuid5(NAMESPACE_URL, f"event-cancellation-recorded:event-1:{recipient}")
            ),
            "payload": {"event_request_id": "event-1", "event_name": "Dinner"},
        }
        for recipient in ["organiser-1", "coord-1"]
    ]


# AC1-P1 (partition): One person who is both Organiser and Coordinator gets one notice.
def test_one_person_in_both_roles_is_told_once() -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    events.rows[event_id]["organiser_id"] = "coord-1"
    spy = OwnerSpy()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert [call["recipient_ids"] for call in spy.recorded] == [["coord-1"]]


# AC1-P2 (partition): With no registered Attendee the Organiser and Coordinator are
# still told, and no Attendee notice is sent.
def test_no_attendees_still_tells_the_organiser_and_coordinator() -> None:
    client, _, event_id = eligible_fixture("Planning")
    spy = OwnerSpy()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert [call["recipient_ids"] for call in spy.recorded] == [["organiser-1", "coord-1"]]
    assert spy.cancelled == []


# AC1-X1 (cross-cutting): Attendees are still told as before, with their own notice.
def test_attendee_notices_are_unchanged() -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    events.registered_attendees[event_id] = list(ATTENDEES)
    spy = OwnerSpy()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert [call["attendee_ids"] for call in spy.cancelled] == [ATTENDEES]
    assert [call["recipient_ids"] for call in spy.recorded] == [["organiser-1", "coord-1"]]


@pytest.mark.parametrize(
    ("status", "caller", "expected"),
    [("Completed", "coord-1", 409), ("Confirmed", "coord-2", 403)],
    ids=["AC1-N1a", "AC1-N1b"],
)
# AC1-N1 (negative): A refused cancellation (terminal status, not the assigned
# Coordinator) leaves the event alone and tells nobody.
def test_refused_cancellation_tells_nobody(status: str, caller: str, expected: int) -> None:
    client, events, event_id = eligible_fixture(status)
    spy = OwnerSpy()
    with_spy(client, spy)

    with client:
        response = cancel(client, event_id, caller)

    assert response.status_code == expected
    assert events.rows[event_id]["status"] == status
    assert spy.recorded == []


# AC1-N2 (negative): If the Coordinator cannot be looked up, the cancellation stands and
# the Organiser is still told.
def test_coordinator_lookup_failure_still_tells_the_organiser(monkeypatch) -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    spy = OwnerSpy()
    with_spy(client, spy)

    def lookup_fails(event_request_id: str) -> str:
        raise SupabaseRepositoryError("Supabase is down")

    monkeypatch.setattr(events, "latest_coordinator_id", lookup_fails)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert events.rows[event_id]["status"] == "Cancelled"
    assert [call["recipient_ids"] for call in spy.recorded] == [["organiser-1"]]


# AC1-N3 (negative): An unreachable notification service never blocks the cancellation.
def test_notification_outage_does_not_block_the_cancellation(monkeypatch) -> None:
    client, events, event_id = eligible_fixture("Confirmed")
    with_spy(client, NotificationClient(NOTIFICATIONS_URL))

    def unreachable(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", unreachable)

    with client:
        response = cancel(client, event_id)

    assert response.status_code == 200
    assert events.rows[event_id]["status"] == "Cancelled"


# AC1-B1 (boundary): Cancelling an already cancelled event is refused and tells nobody
# a second time.
def test_cancelling_twice_tells_nobody_twice() -> None:
    client, _, event_id = eligible_fixture("Confirmed")
    spy = OwnerSpy()
    with_spy(client, spy)

    with client:
        first = cancel(client, event_id)
        second = cancel(client, event_id)

    assert (first.status_code, second.status_code) == (200, 409)
    assert len(spy.recorded) == 1
