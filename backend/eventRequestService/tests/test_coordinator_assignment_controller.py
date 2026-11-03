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


# AC2-H1 (happy, SCRUM-14): an Operations Manager can assign a Coordinator to a Submitted request
# Purpose: Confirms an Operations Manager can assign a Coordinator.
def test_assign_coordinator_to_submitted_request() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )

    assert response.status_code == 201
    assert response.json()["event_request_id"] == event_request_id
    assert response.json()["coordinator_id"] == "coord-1"
    assert response.json()["assigned_by"] == "ops-1"


# AC3-H1 (happy, SCRUM-14): assignment records the Coordinator without advancing the status
# Purpose: Assignment alone does not change the event request status.
def test_assign_coordinator_does_not_change_event_request_status() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )

    assert event_requests.rows[event_request_id]["status"] == "Submitted"


# AC2-N1 (negative, SCRUM-14): a Draft refuses assignment and leaves no row behind
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
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )

    assert response.status_code == 409


# AC2-N2 (negative, SCRUM-14): Completed, Cancelled and Rejected all refuse assignment
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
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )

    assert response.status_code == 409


# AC2-N3 (negative, SCRUM-14): an unknown request 404s instead of being assigned
# Purpose: 404s rather than assigning a Coordinator to a missing request.
def test_assign_coordinator_to_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )

    assert response.status_code == 404


# AC4-N1 (negative, SCRUM-28): a database-side state conflict raised after the
# pre-check still maps to 409, never 500, and writes nothing
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
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )

    assert response.status_code == 409


# AC4-N2, AC5 (negative, SCRUM-28): an invalid target is refused (P0005) after the
# pre-check, surfacing as a conflict without creating an assignment
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
            json={"coordinator_id": "attendee-1", "expected_coordinator_id": None},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "The selected user is not an Event Coordinator"


# AC6-H1, AC3 (happy, SCRUM-14): reassignment returns the latest Coordinator,
# preserves history and never advances the status
# Purpose: Reassignment inserts a new row rather than overwriting, preserving history.
def test_reassignment_preserves_history_and_get_returns_latest() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )
        client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-2", "expected_coordinator_id": "coord-1"},
        )
        current = client.get(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
        )

    assert current.status_code == 200
    assert current.json()["coordinator_id"] == "coord-2"


# AC3-N1 (negative, SCRUM-14): no assignment yet is a 404, distinct from a missing request
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


# AC2-N4 (negative, SCRUM-14): both endpoints reject requests without a verified session
# Purpose: Ensures both endpoints reject requests without a verified session.
def test_requires_bearer_session() -> None:
    app = create_app(FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository())
    with TestClient(app) as client:
        assign = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/coordinator",
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )
        get = client.get(
            "/event-requests/00000000-0000-0000-0000-000000000001/coordinator"
        )

    assert assign.status_code == 401
    assert get.status_code == 401


# AC2-N5 (negative, SCRUM-14): a caller without the Operations Manager role is refused 403
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
                json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


# AC2-P1 (partition, SCRUM-14): an Operations Manager holding the role among several may assign
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
                json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 201
    assert response.json()["assigned_by"] == caller_id


# AC1-H1 (happy, SCRUM-14): the queue lists Submitted requests that still need a Coordinator
# Purpose: Lists submitted requests that still need a Coordinator.
def test_awaiting_assignment_lists_submitted_requests_without_a_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.get("/event-requests/awaiting-assignment", headers=headers())

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [event_request_id]


# AC1-P1 (partition, SCRUM-14): assigned requests drop out of the awaiting queue
# Purpose: A request drops out of the queue once it has a Coordinator.
def test_awaiting_assignment_excludes_requests_that_have_a_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        assigned_id = submit_event_request(event_requests)
        unassigned_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{assigned_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )
        response = client.get("/event-requests/awaiting-assignment", headers=headers())

    assert [row["id"] for row in response.json()] == [unassigned_id]


# AC1-P2 (partition, SCRUM-14): only Submitted requests belong in the queue and an
# empty queue answers 200 [], not 404
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


# AC1-N1 (negative, SCRUM-14): the awaiting-assignment queue is closed to non-managers
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


# AC5-P1 (partition, SCRUM-28): coordinator details are visible to the owning organiser,
# the assigned coordinator and the Operations Manager — nobody else (404/403)
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


# AC6-H6 (happy, SCRUM-14): the overview lists each assigned request once with the
# latest Coordinator, so the manager can find requests to reassign
# Purpose: SCRUM-14 AC6 — a manager can find assigned requests to reassign them,
# and sees the latest Coordinator rather than the first.
def test_current_assignments_list_the_latest_coordinator_per_request() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        assigned_id = submit_event_request(event_requests)
        submit_event_request(event_requests)  # never assigned
        previous = None
        for coordinator_id in ("coord-1", "coord-2"):
            client.post(
                f"/event-requests/{assigned_id}/coordinator",
                headers=headers(),
                json={"coordinator_id": coordinator_id, "expected_coordinator_id": previous},
            )
            previous = coordinator_id
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert [row["event_request"]["id"] for row in body] == [assigned_id]
    assert body[0]["assignment"]["coordinator_id"] == "coord-2"


# AC6-P1 (partition, SCRUM-14): terminal requests leave the reassignment overview
# Purpose: Closed requests cannot be reassigned, so they are not offered.
def test_current_assignments_exclude_terminal_requests() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        closed_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{closed_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )
        event_requests.rows[closed_id]["status"] = "Cancelled"
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    assert response.json() == []


# AC6-P2 (partition, SCRUM-14): requests stay reassignable once review has started
# Purpose: Requests keep appearing once review has started, so they stay reassignable.
def test_current_assignments_include_requests_under_review() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )
        event_requests.rows[request_id]["status"] = "Under Review"
        response = client.get("/event-requests/assignments", headers=headers())

    assert [row["event_request"]["id"] for row in response.json()] == [request_id]


# AC6-N1 (negative, SCRUM-14): the assignments overview is closed to non-managers
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
            json={"coordinator_id": "coord-1", "expected_coordinator_id": None},
        )
        event_requests.rows[request_id]["status"] = "Safety Review"
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    assert [row["event_request"]["id"] for row in response.json()] == [request_id]


def _assign(client: TestClient, event_request_id: str, coordinator_id: str, expected: str | None):
    return client.post(
        f"/event-requests/{event_request_id}/coordinator",
        headers=headers(),
        json={"coordinator_id": coordinator_id, "expected_coordinator_id": expected},
    )


# AC6-H1 (happy, SCRUM-62): a reassignment that names the Coordinator the Lead saw is saved
def test_reassignment_from_a_current_view_is_saved() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        _assign(client, event_request_id, "coord-1", None)
        response = _assign(client, event_request_id, "coord-2", "coord-1")

    assert response.status_code == 201
    assert response.json()["coordinator_id"] == "coord-2"


# AC6-N1 (negative, SCRUM-62): a reassignment from a stale view is refused (409) and the
# current Coordinator stays
def test_reassignment_from_a_stale_view_is_refused() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        _assign(client, event_request_id, "coord-1", None)
        _assign(client, event_request_id, "coord-2", "coord-1")
        response = _assign(client, event_request_id, "coord-3", "coord-1")  # saw coord-1, now coord-2

    assert response.status_code == 409
    assert coordinators.latest_for_event_request(event_request_id)["coordinator_id"] == "coord-2"
    assert len(coordinators.rows) == 2


# AC6-N2 (negative, SCRUM-62): a first assignment from a view that showed nobody is
# refused when someone was assigned meanwhile
def test_first_assignment_is_refused_when_someone_was_assigned_meanwhile() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        _assign(client, event_request_id, "coord-1", None)
        response = _assign(client, event_request_id, "coord-2", None)

    assert response.status_code == 409
    assert len(coordinators.rows) == 1


# AC6-N3 (negative, SCRUM-62): a request that does not state the view it was made from is refused
def test_assignment_without_the_expected_coordinator_is_refused() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.post(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert response.status_code == 422
    assert coordinators.rows == []


# AC3-P4 (partition, SCRUM-62): a Postponed event is still active, so the Lead sees it
def test_current_assignments_include_postponed_requests() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        request_id = submit_event_request(event_requests)
        _assign(client, request_id, "coord-1", None)
        event_requests.rows[request_id]["status"] = "Postponed"
        response = client.get("/event-requests/assignments", headers=headers())

    assert [row["event_request"]["id"] for row in response.json()] == [request_id]


# AC7-N1 (negative, SCRUM-14): a Withdrawn request refuses assignment
def test_assign_coordinator_refused_once_withdrawn() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        event_requests.rows[event_request_id]["status"] = "Withdrawn"
        response = _assign(client, event_request_id, "coord-1", None)

    assert response.status_code == 409
