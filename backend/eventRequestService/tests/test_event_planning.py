"""SCRUM-58 AC1 and AC4: the assigned coordinator moves an Approved event into
Planning; everyone else is refused and nothing changes. The history row is
written by the database trigger, so it is proven in the DB layer (AC1-X1), not here."""
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)
from test_event_transition_controller import (
    assign_coordinator,
    headers,
    make_assigned_client,
    make_client,
)

from app.main import create_app


def planning_path(event_request_id: str) -> str:
    return f"/event-requests/{event_request_id}/planning"


# AC1-H1 (happy): the assigned coordinator moves an Approved event into Planning
def test_assigned_coordinator_starts_planning_approved_event() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status="Approved"
    )
    with client:
        response = client.post(
            planning_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == event_request_id
    assert body["status"] == "Planning"
    assert event_requests.rows[event_request_id]["status"] == "Planning"


@pytest.mark.parametrize(
    "from_status",
    [
        "Submitted",
        "Under Review",
        "Changes Requested",
        "Rejected",
        "Planning",
        "Confirmed",
        "Completed",
        "Cancelled",
    ],
    ids=[f"AC1-P{k}" for k in range(1, 9)],
)
# AC1-P1..P8 (partition): planning starts only from Approved; every other status is refused unchanged
def test_start_planning_refused_from_other_than_approved(from_status: str) -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status=from_status
    )
    with client:
        response = client.post(
            planning_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 409
    assert event_requests.rows[event_request_id]["status"] == from_status


# AC1-N1 (negative): a request that does not exist is a 404, not a guess
def test_start_planning_for_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            planning_path("00000000-0000-0000-0000-000000000001"),
            headers=headers("coord-1"),
        )

    assert response.status_code == 404
    # The service's message, not FastAPI's "Not Found" for a route that doesn't exist.
    assert response.json() == {
        "detail": "Event request 00000000-0000-0000-0000-000000000001 was not found"
    }


# AC4-N1 (negative): a coordinator who is not assigned is refused and the status stays Approved
def test_start_planning_refused_for_non_assigned_coordinator() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        coordinator_id="coord-2", status="Approved"
    )
    with client:
        response = client.post(
            planning_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Approved"


# AC4-N2 (negative): a coordinator reassigned away is refused — the latest assignment wins
def test_start_planning_refused_for_reassigned_away_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    event_request_id = submit_event_request(event_requests)
    event_requests.rows[event_request_id]["status"] = "Approved"
    assign_coordinator(coordinators, event_request_id, "coord-1")
    assign_coordinator(coordinators, event_request_id, "coord-2")

    with make_client(event_requests, coordinators) as client:
        response = client.post(
            planning_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Approved"


# AC4-N3 (negative): with no coordinator assigned at all, planning is refused
def test_start_planning_refused_when_unassigned() -> None:
    event_requests = FakeEventRequestRepository()
    event_request_id = submit_event_request(event_requests)
    event_requests.rows[event_request_id]["status"] = "Approved"

    with make_client(event_requests) as client:
        response = client.post(
            planning_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Approved"


# AC4-N4 (negative): a caller with no session is refused before anything is read
def test_start_planning_requires_bearer_session() -> None:
    app = create_app(
        FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository()
    )
    with TestClient(app) as client:
        response = client.post(
            planning_path("00000000-0000-0000-0000-000000000001")
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "role",
    ["event_organiser", "event_operations_manager"],
    ids=["AC4-N5", "AC4-N6"],
)
# AC4-N5, N6 (negative): non-coordinator roles are refused even when their ID matches the assignment
def test_start_planning_requires_coordinator_role(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    caller_id = str(uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200, json={"id": caller_id, "role": role, "roles": [role]}
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    try:
        app = create_app(event_requests, coordinators)
        event_request_id = submit_event_request(event_requests)
        event_requests.rows[event_request_id]["status"] = "Approved"
        assign_coordinator(coordinators, event_request_id, caller_id)
        with TestClient(app) as client:
            response = client.post(
                planning_path(event_request_id),
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Approved"
