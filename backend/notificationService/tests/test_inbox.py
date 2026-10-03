from uuid import uuid4

import pytest
from fakes import FakeNotificationRepository, make_client, signed_in_as
from fastapi.testclient import TestClient

from app.main import create_app


def repository_with(*events: tuple[str, str]) -> FakeNotificationRepository:
    """Store (recipient_id, event_type) pairs in order, oldest first."""
    repository = FakeNotificationRepository()
    for recipient_id, event_type in events:
        repository.save(
            event_type=event_type,
            recipient_id=recipient_id,
            payload={"event_request_id": "11111111-1111-4111-8111-111111111111"},
            event_id=None,
        )
    return repository


# Purpose: The inbox is private: it needs a signed-in user.
@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/notifications"), ("PATCH", f"/notifications/{uuid4()}/read")],
)
def test_inbox_requires_sign_in(method: str, path: str) -> None:
    with TestClient(create_app(FakeNotificationRepository())) as client:
        response = client.request(method, path)

    assert response.status_code == 401


# Purpose: A user sees only their own notifications, newest first (SCRUM-37
# relevance: nobody reads notifications meant for someone else).
def test_lists_only_the_callers_notifications_newest_first() -> None:
    repository = repository_with(
        ("coord-1", "coordinator_assigned"),
        ("someone-else", "coordinator_assigned"),
        ("coord-1", "event.cancelled"),
    )
    with make_client(repository) as client:
        response = client.get("/notifications", headers=signed_in_as("coord-1"))

    assert response.status_code == 200
    assert [item["event_type"] for item in response.json()] == [
        "event.cancelled",
        "coordinator_assigned",
    ]


# Purpose: The response carries what the inbox shows, and nothing internal.
def test_list_items_have_the_inbox_fields() -> None:
    repository = repository_with(("coord-1", "coordinator_assigned"))
    with make_client(repository) as client:
        item = client.get("/notifications", headers=signed_in_as("coord-1")).json()[0]

    assert set(item) == {"id", "event_type", "payload", "read_at", "created_at"}
    assert item["read_at"] is None
    assert item["payload"] == {
        "event_request_id": "11111111-1111-4111-8111-111111111111"
    }


# Purpose: "Unread only" hides notifications the user has already read.
def test_can_list_only_unread_notifications() -> None:
    repository = repository_with(
        ("coord-1", "coordinator_assigned"), ("coord-1", "event.cancelled")
    )
    repository.rows[0]["read_at"] = "2026-09-29T12:00:00+00:00"
    with make_client(repository) as client:
        response = client.get(
            "/notifications?unread_only=true", headers=signed_in_as("coord-1")
        )

    assert [item["event_type"] for item in response.json()] == ["event.cancelled"]


# Purpose: The list is capped so one request cannot pull an unbounded inbox.
def test_limit_caps_the_list() -> None:
    repository = repository_with(*[("coord-1", "coordinator_assigned")] * 3)
    with make_client(repository) as client:
        response = client.get("/notifications?limit=2", headers=signed_in_as("coord-1"))

    assert len(response.json()) == 2


@pytest.mark.parametrize("limit", [0, 101])
# Purpose: Out-of-range limits are refused rather than silently adjusted.
def test_rejects_an_out_of_range_limit(limit: int) -> None:
    with make_client(FakeNotificationRepository()) as client:
        response = client.get(
            f"/notifications?limit={limit}", headers=signed_in_as("coord-1")
        )

    assert response.status_code == 422


# Purpose: A user can mark their own notification as read.
def test_marks_the_callers_notification_as_read() -> None:
    repository = repository_with(("coord-1", "coordinator_assigned"))
    notification_id = repository.rows[0]["id"]
    with make_client(repository) as client:
        response = client.patch(
            f"/notifications/{notification_id}/read", headers=signed_in_as("coord-1")
        )

    assert response.status_code == 200
    assert response.json()["id"] == notification_id
    assert response.json()["read_at"] is not None


# Purpose: Someone else's notification looks exactly like a missing one, so
# ids cannot be probed and nobody can mark another person's notification.
def test_cannot_mark_someone_elses_notification() -> None:
    repository = repository_with(("coord-1", "coordinator_assigned"))
    notification_id = repository.rows[0]["id"]
    with make_client(repository) as client:
        theirs = client.patch(
            f"/notifications/{notification_id}/read",
            headers=signed_in_as("someone-else"),
        )
        missing = client.patch(
            f"/notifications/{uuid4()}/read", headers=signed_in_as("someone-else")
        )

    assert (theirs.status_code, missing.status_code) == (404, 404)
    assert theirs.json() == missing.json()
    assert repository.rows[0]["read_at"] is None


# Purpose: A malformed id is refused before the database is asked.
def test_rejects_a_malformed_notification_id() -> None:
    with make_client(FakeNotificationRepository()) as client:
        response = client.patch(
            "/notifications/not-a-uuid/read", headers=signed_in_as("coord-1")
        )

    assert response.status_code == 422


# Purpose: A database outage is a 502, never an empty inbox that hides it.
def test_reports_a_store_failure_as_bad_gateway() -> None:
    repository = FakeNotificationRepository()
    repository.fail = True
    with make_client(repository) as client:
        response = client.get("/notifications", headers=signed_in_as("coord-1"))

    assert response.status_code == 502
