"""POST /events/{id}/coordinator — Operations Manager assigns a Coordinator
to a submitted event.
"""

from conftest import (
    COORDINATOR,
    OPERATIONS_MANAGER,
    ORGANISER,
    OTHER_COORDINATOR,
    create_event,
)
from fastapi.testclient import TestClient


def _submit(client: TestClient, event_id: str) -> None:
    response = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "submitted"},
        headers=ORGANISER,
    )
    assert response.status_code == 200


def test_operations_manager_can_assign_coordinator(client: TestClient) -> None:
    event_id = create_event(client)
    _submit(client, event_id)

    response = client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["coordinator_id"] == "coord-1"
    assert body["status"] == "submitted"  # assignment alone doesn't move status


def test_non_operations_manager_cannot_assign(client: TestClient) -> None:
    event_id = create_event(client)
    _submit(client, event_id)

    response = client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=ORGANISER,
    )

    assert response.status_code == 403


def test_cannot_assign_before_submission(client: TestClient) -> None:
    event_id = create_event(client)

    response = client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 409


def test_cannot_assign_to_a_terminal_event(client: TestClient) -> None:
    event_id = create_event(client)
    _submit(client, event_id)
    cancel = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "cancelled"},
        headers=ORGANISER,
    )
    assert cancel.status_code == 200

    response = client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 409


def test_reassign_to_a_different_coordinator(client: TestClient) -> None:
    event_id = create_event(client)
    _submit(client, event_id)
    client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    response = client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-2"},
        headers=OPERATIONS_MANAGER,
    )

    assert response.status_code == 200
    assert response.json()["coordinator_id"] == "coord-2"


def test_previous_coordinator_loses_cancel_rights_after_reassignment(
    client: TestClient,
) -> None:
    event_id = create_event(client)
    _submit(client, event_id)
    client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-2"},
        headers=OPERATIONS_MANAGER,
    )

    refused = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "cancelled"},
        headers=COORDINATOR,
    )
    assert refused.status_code == 403

    allowed = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "cancelled"},
        headers=OTHER_COORDINATOR,
    )
    assert allowed.status_code == 200


def test_previous_coordinator_loses_complete_rights_after_reassignment(
    client: TestClient,
) -> None:
    event_id = create_event(client)
    _submit(client, event_id)
    client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-1"},
        headers=OPERATIONS_MANAGER,
    )

    for target in ["under_review", "approved", "planning", "confirmed"]:
        response = client.post(
            f"/events/{event_id}/status",
            json={"target_status": target},
            headers=ORGANISER,
        )
        assert response.status_code == 200, response.json()

    client.post(
        f"/events/{event_id}/coordinator",
        json={"coordinator_id": "coord-2"},
        headers=OPERATIONS_MANAGER,
    )

    refused = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "completed"},
        headers=COORDINATOR,
    )
    assert refused.status_code == 403

    allowed = client.post(
        f"/events/{event_id}/status",
        json={"target_status": "completed"},
        headers=OTHER_COORDINATOR,
    )
    assert allowed.status_code == 200
