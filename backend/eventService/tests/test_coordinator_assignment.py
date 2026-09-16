"""POST/GET /event-requests/{id}/coordinator — Operations Manager assigns a
Coordinator to a submitted event request.
"""

from conftest import (
    COORDINATOR,
    OPERATIONS_MANAGER,
    ORGANISER,
    OTHER_COORDINATOR,
    seed_event_request,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker


def test_operations_manager_can_assign_coordinator(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_request_id = seed_event_request(session_factory, status="Submitted")

    response = client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["coordinator_id"] == "coord-1"
    assert body["event_request_id"] == str(event_request_id)
    assert body["assigned_by"] == "ops-1"


def test_non_operations_manager_cannot_assign(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_request_id = seed_event_request(session_factory, status="Submitted")

    response = client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=ORGANISER,
    )

    assert response.status_code == 403


def test_cannot_assign_before_submission(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_request_id = seed_event_request(session_factory, status="Draft")

    response = client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 409


def test_cannot_assign_to_a_terminal_request(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_request_id = seed_event_request(session_factory, status="Cancelled")

    response = client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 409


def test_assigning_unknown_event_request_is_404(client: TestClient) -> None:
    response = client.post(
        "/event-requests/00000000-0000-0000-0000-000000000000/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 404


def test_reassign_to_a_different_coordinator(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_request_id = seed_event_request(session_factory, status="Submitted")
    client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    response = client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-2"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 201
    assert response.json()["coordinator_id"] == "coord-2"


def test_get_current_coordinator_returns_the_latest_assignment(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_request_id = seed_event_request(session_factory, status="Submitted")
    client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )
    client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-2"},
        headers=OPERATIONS_MANAGER,
    )

    response = client.get(f"/event-requests/{event_request_id}/coordinator")

    assert response.status_code == 200
    assert response.json()["coordinator_id"] == "coord-2"


def test_get_current_coordinator_404_before_any_assignment(
    client: TestClient, session_factory: sessionmaker
) -> None:
    event_request_id = seed_event_request(session_factory, status="Submitted")

    response = client.get(f"/event-requests/{event_request_id}/coordinator")

    assert response.status_code == 404


def test_assignment_history_is_preserved_across_reassignment(
    client: TestClient, session_factory: sessionmaker
) -> None:
    """Reassigning inserts a new row rather than overwriting — both
    coordinators should still be discoverable via the coordinator_id each
    was assigned under (proxy for "history isn't lost": we can't list
    history via the API yet, but nothing should have been deleted)."""
    event_request_id = seed_event_request(session_factory, status="Submitted")
    client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )
    client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-2"},
        headers=OPERATIONS_MANAGER,
    )

    from app.models import EventCoordinatorAssignment

    with session_factory() as db:
        rows = (
            db.query(EventCoordinatorAssignment)
            .filter_by(event_request_id=event_request_id)
            .all()
        )
    assert {row.coordinator_id for row in rows} == {"coord-1", "coord-2"}


def test_only_assigned_coordinator_can_be_identified_for_permission_checks(
    client: TestClient, session_factory: sessionmaker
) -> None:
    """Sanity check for the contract eventRequestService's status logic
    relies on: GET .../coordinator reflects who's currently assigned, so it
    can gate cancel/complete against that."""
    event_request_id = seed_event_request(session_factory, status="Submitted")
    client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )
    client.post(
        f"/event-requests/{event_request_id}/coordinator",
        json={"coordinator_id": "coord-2"},
        headers=OPERATIONS_MANAGER,
    )

    current = client.get(f"/event-requests/{event_request_id}/coordinator").json()

    assert current["coordinator_id"] == OTHER_COORDINATOR["X-User-Id"]
    assert current["coordinator_id"] != COORDINATOR["X-User-Id"]
