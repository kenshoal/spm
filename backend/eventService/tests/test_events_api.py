"""API-level tests for event creation, status transitions, and discard."""

from conftest import COORDINATOR, ORGANISER, OTHER_COORDINATOR, create_event
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models import Event


def test_create_event_starts_in_draft(client: TestClient) -> None:
    response = client.post("/events", json={"title": "Orientation"}, headers=ORGANISER)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["organiser_id"] == "org-1"
    assert body["coordinator_id"] is None


def test_submit_transition(client: TestClient) -> None:
    event_id = create_event(client)

    response = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "submitted"},
        headers=ORGANISER,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"


def test_disallowed_transition_is_refused(client: TestClient) -> None:
    event_id = create_event(client)

    response = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "confirmed"},
        headers=ORGANISER,
    )

    assert response.status_code == 409


def test_cancel_without_assigned_coordinator_is_allowed(client: TestClient) -> None:
    event_id = create_event(client)

    response = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "cancelled"},
        headers=ORGANISER,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_only_assigned_coordinator_can_cancel(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_id = create_event(client)

    with session_factory() as db:
        event = db.get(Event, event_id)
        event.coordinator_id = "coord-1"
        db.commit()

    refused = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "cancelled"},
        headers=OTHER_COORDINATOR,
    )
    assert refused.status_code == 403

    allowed = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "cancelled"},
        headers=COORDINATOR,
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "cancelled"


def test_complete_requires_coordinator_role(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_id = create_event(client)
    with session_factory() as db:
        event = db.get(Event, event_id)
        event.coordinator_id = "coord-1"
        db.commit()

    for target in ["submitted", "under_review", "approved", "planning", "confirmed"]:
        response = client.post(
            f"/events/{event_id}/status",
            json={"target_status": target},
            headers=ORGANISER,
        )
        assert response.status_code == 200, response.json()

    refused = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "completed"},
        headers=ORGANISER,
    )
    assert refused.status_code == 403

    allowed = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "completed"},
        headers=COORDINATOR,
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "completed"


def test_discard_draft_by_organiser(client: TestClient) -> None:
    event_id = create_event(client)

    response = client.delete(f"/events/{event_id}", headers=ORGANISER)

    assert response.status_code == 204
    assert client.get(f"/events/{event_id}").status_code == 404


def test_discard_refused_for_non_organiser(client: TestClient) -> None:
    event_id = create_event(client)

    response = client.delete(f"/events/{event_id}", headers=COORDINATOR)

    assert response.status_code == 403


def test_discard_refused_once_submitted(client: TestClient) -> None:
    event_id = create_event(client)
    client.post(
        f"/events/{event_id}/status",
        json={"target_status": "submitted"},
        headers=ORGANISER,
    )

    response = client.delete(f"/events/{event_id}", headers=ORGANISER)

    assert response.status_code == 409
