"""SCRUM-57 AC1: the Organiser and the assigned Coordinator are told when an event is
cancelled. Case IDs match docs/testcases/scrum_57_testcases.md.
"""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
from test_attendee_event_notification import SpyNotificationClient, cancel, with_spy
from test_event_change_request import eligible_fixture

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
