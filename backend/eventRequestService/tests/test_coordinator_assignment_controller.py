from uuid import uuid4

import httpx
import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)

from app.controllers.coordinator_assignment_controller import (
    get_operations_manager_id,
)
from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
    get_authenticated_user_id,
    get_organiser_id,
)
from app.main import create_app
from app.repositories import CoordinatorAssignmentRpcError


def make_client(
    event_request_repository: FakeEventRequestRepository | None = None,
    coordinator_repository: FakeCoordinatorAssignmentRepository | None = None,
) -> TestClient:
    app = create_app(
        event_request_repository or FakeEventRequestRepository(),
        coordinator_repository or FakeCoordinatorAssignmentRepository(),
    )

    def fake_caller_id(authorization: str = Header()) -> str:
        return authorization.removeprefix("Bearer ")

    app.dependency_overrides[get_organiser_id] = fake_caller_id
    app.dependency_overrides[get_authenticated_user_id] = fake_caller_id
    app.dependency_overrides[get_operations_manager_id] = fake_caller_id
    app.dependency_overrides[get_authenticated_caller] = lambda: AuthenticatedCaller(
        id="ops-1", roles=("event_operations_manager",)
    )
    return TestClient(app)


def headers(caller_id: str = "ops-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {caller_id}"}


# Purpose: Confirms an Operations Manager can assign a Coordinator.
def test_assign_coordinator_to_submitted_request() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert response.status_code == 201
    assert response.json()["event_request_id"] == event_request_id
    assert response.json()["coordinator_id"] == "coord-1"
    assert response.json()["assigned_by"] == "ops-1"


# Purpose: Assignment alone does not change the event request status.
def test_assign_coordinator_does_not_change_event_request_status() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert event_requests.rows[event_request_id]["status"] == "Submitted"


# Purpose: Refuses assignment before the request has been submitted.
def test_assign_coordinator_refused_before_submission() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        created = client.post(
            "/event-requests",
            headers={"Authorization": "Bearer organiser-1"},
            json={"event_name": "Still a draft"},
        ).json()
        response = client.post(
            f"/event-requests/{created['id']}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert response.status_code == 409


# Purpose: Refuses assignment once the request has reached a terminal status.
@pytest.mark.parametrize("status", ["Completed", "Cancelled", "Rejected"])
def test_assign_coordinator_refused_once_terminal(status: str) -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        event_requests.rows[event_request_id]["status"] = status
        response = client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert response.status_code == 409


# Purpose: 404s rather than assigning a Coordinator to a missing request.
def test_assign_coordinator_to_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert response.status_code == 404


# Purpose: A concurrent state change rejected by the database must remain a conflict.
def test_atomic_assignment_status_rejection_returns_conflict() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)

    def reject_after_precheck(values: dict[str, object]) -> dict[str, object]:
        raise CoordinatorAssignmentRpcError("state changed", errcode="P0004")

    coordinators.create = reject_after_precheck  # type: ignore[method-assign]
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert response.status_code == 409


# Purpose: The database role check prevents assigning a non-coordinator identity.
def test_atomic_assignment_target_role_rejection_returns_conflict() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)

    def reject_non_coordinator(values: dict[str, object]) -> dict[str, object]:
        raise CoordinatorAssignmentRpcError("wrong role", errcode="P0005")

    coordinators.create = reject_non_coordinator  # type: ignore[method-assign]
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "attendee-1"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "The selected user is not an Event Coordinator"


# Purpose: Reassignment inserts a new row rather than overwriting, preserving history.
def test_reassignment_preserves_history_and_get_returns_latest() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )
        client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-2"},
        )
        current = client.get(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
        )

    assert current.status_code == 200
    assert current.json()["coordinator_id"] == "coord-2"


# Purpose: 404s when no Coordinator has been assigned yet.
def test_get_coordinator_when_none_assigned() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.get(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
        )

    assert response.status_code == 404


# Purpose: Ensures both endpoints reject requests without a verified session.
def test_requires_bearer_session() -> None:
    app = create_app(FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository())
    with TestClient(app) as client:
        assign = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/coordinator",
            json={"coordinator_id": "coord-1"},
        )
        get = client.get(
            "/event-requests/00000000-0000-0000-0000-000000000001/coordinator"
        )

    assert assign.status_code == 401
    assert get.status_code == 401


# Purpose: Refuses assignment for a caller who is not an Operations Manager.
def test_assign_coordinator_requires_operations_manager_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller_id = str(uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "id": caller_id,
                "email": None,
                "role": "event_coordinator",
                "roles": ["event_coordinator"],
            },
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    event_requests = FakeEventRequestRepository()
    try:
        app = create_app(event_requests, FakeCoordinatorAssignmentRepository())
        with TestClient(app) as client:
            event_request_id = submit_event_request(event_requests)
            response = client.post(
                f"/event-requests/{event_request_id}/coordinator",
                headers={"Authorization": "Bearer valid-token"},
                json={"coordinator_id": "coord-1"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


# Purpose: Allows assignment when any caller role is Event Operations Manager.
def test_assign_coordinator_allows_event_operations_manager_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller_id = str(uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "id": caller_id,
                "email": None,
                "role": "venue_staff",
                "roles": ["venue_staff", "event_operations_manager"],
            },
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    event_requests = FakeEventRequestRepository()
    try:
        app = create_app(event_requests, FakeCoordinatorAssignmentRepository())
        with TestClient(app) as client:
            event_request_id = submit_event_request(event_requests)
            response = client.post(
                f"/event-requests/{event_request_id}/coordinator",
                headers={"Authorization": "Bearer valid-token"},
                json={"coordinator_id": "coord-1"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 201
    assert response.json()["assigned_by"] == caller_id


# Purpose: Lists submitted requests that still need a Coordinator.
def test_awaiting_assignment_lists_submitted_requests_without_a_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.get("/event-requests/awaiting-assignment", headers=headers())

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [event_request_id]


# Purpose: A request drops out of the queue once it has a Coordinator.
def test_awaiting_assignment_excludes_requests_that_have_a_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        assigned_id = submit_event_request(event_requests)
        unassigned_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{assigned_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )
        response = client.get("/event-requests/awaiting-assignment", headers=headers())

    assert [row["id"] for row in response.json()] == [unassigned_id]


# Purpose: Only Submitted requests belong in the Operations Manager queue.
def test_awaiting_assignment_excludes_drafts() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        client.post(
            "/event-requests",
            headers={"Authorization": "Bearer organiser-1"},
            json={"event_name": "Still a draft"},
        )
        response = client.get("/event-requests/awaiting-assignment", headers=headers())

    assert response.status_code == 200
    assert response.json() == []


# Purpose: Confirms the queue is closed to non-Operations Manager callers.
def test_awaiting_assignment_requires_operations_manager_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "id": str(uuid4()),
                "email": None,
                "role": "event_coordinator",
                "roles": ["event_coordinator"],
            },
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        app = create_app(
            FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository()
        )
        with TestClient(app) as client:
            response = client.get(
                "/event-requests/awaiting-assignment",
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


# Purpose: Assignment details are scoped to users with a request relationship.
@pytest.mark.parametrize(
    ("roles", "relationship", "expected_status"),
    [
        (("event_organiser",), "owner", 200),
        (("event_organiser",), "other", 404),
        (("event_operations_manager",), "other", 200),
        (("event_coordinator",), "assigned", 200),
        (("event_coordinator",), "other", 404),
        (("venue_staff",), "other", 403),
        (("venue_staff", "event_coordinator"), "assigned", 200),
    ],
)
def test_get_coordinator_is_scoped_to_request_access(
    roles: tuple[str, ...],
    relationship: str,
    expected_status: int,
) -> None:
    caller_id = str(uuid4())
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    app = create_app(event_requests, coordinators)
    app.dependency_overrides[get_authenticated_caller] = lambda: AuthenticatedCaller(
        id=caller_id, roles=roles
    )

    event_request_id = submit_event_request(event_requests)
    if relationship == "owner":
        event_requests.rows[event_request_id]["organiser_id"] = caller_id
    coordinators.create(
        {
            "event_request_id": event_request_id,
            "coordinator_id": (
                caller_id if relationship == "assigned" else str(uuid4())
            ),
            "assigned_by": str(uuid4()),
        }
    )

    with TestClient(app) as client:
        response = client.get(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers("valid-token"),
        )

    assert response.status_code == expected_status


# Purpose: SCRUM-14 AC6 — a manager can find assigned requests to reassign them,
# and sees the latest Coordinator rather than the first.
def test_current_assignments_list_the_latest_coordinator_per_request() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        assigned_id = submit_event_request(event_requests)
        submit_event_request(event_requests)  # never assigned
        for coordinator_id in ("coord-1", "coord-2"):
            client.post(
                f"/event-requests/{assigned_id}/coordinator",
                headers=headers(),
                json={"coordinator_id": coordinator_id},
            )
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert [row["event_request"]["id"] for row in body] == [assigned_id]
    assert body[0]["assignment"]["coordinator_id"] == "coord-2"


# Purpose: Closed requests cannot be reassigned, so they are not offered.
def test_current_assignments_exclude_terminal_requests() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        closed_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{closed_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )
        event_requests.rows[closed_id]["status"] = "Cancelled"
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    assert response.json() == []


# Purpose: Requests keep appearing once review has started, so they stay reassignable.
def test_current_assignments_include_requests_under_review() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )
        event_requests.rows[request_id]["status"] = "Under Review"
        response = client.get("/event-requests/assignments", headers=headers())

    assert [row["event_request"]["id"] for row in response.json()] == [request_id]


# Purpose: The assignment overview is closed to non-Operations Manager callers.
def test_current_assignments_require_operations_manager_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "id": str(uuid4()),
                "email": None,
                "role": "event_coordinator",
                "roles": ["event_coordinator"],
            },
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        app = create_app(
            FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository()
        )
        with TestClient(app) as client:
            response = client.get(
                "/event-requests/assignments",
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


# AC6-P3 (partition, SCRUM-60): an event in Safety Review is still in flight,
# so the Lead can find it and reassign its Coordinator.
def test_current_assignments_include_requests_in_safety_review() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )
        event_requests.rows[request_id]["status"] = "Safety Review"
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    assert [row["event_request"]["id"] for row in response.json()] == [request_id]
