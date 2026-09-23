from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeEventRequestRepository as _BaseFakeEventRequestRepository,
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


class FakeEventRequestRepository(_BaseFakeEventRequestRepository):
    """Adds the unscoped lookup a non-organiser caller (Operations Manager)
    needs — his fake only implements the organiser-scoped methods."""

    def get_by_id(self, event_request_id: str) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        return dict(row) if row is not None else None

    def update_status(
        self, event_request_id: str, from_status: str, to_status: str
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if row is None or row["status"] != from_status:
            return None
        row["status"] = to_status
        return dict(row)

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in reversed(list(self.rows.values()))
            if row["status"] == status
        ]


class FakeCoordinatorAssignmentRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        row = {
            **values,
            "id": len(self.rows) + 1,
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        }
        self.rows.append(row)
        return dict(row)

    def latest_for_event_request(
        self, event_request_id: str
    ) -> dict[str, Any] | None:
        matches = [r for r in self.rows if r["event_request_id"] == event_request_id]
        return dict(matches[-1]) if matches else None

    def assigned_event_request_ids(self, event_request_ids: list[str]) -> set[str]:
        wanted = set(event_request_ids)
        return {r["event_request_id"] for r in self.rows} & wanted


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

    # These tests aren't about authorization, so both dependencies just trust
    # the bearer value as the caller id. The role gate itself is tested
    # separately below, against the real get_operations_manager_id.
    app.dependency_overrides[get_organiser_id] = fake_caller_id
    app.dependency_overrides[get_authenticated_user_id] = fake_caller_id
    app.dependency_overrides[get_operations_manager_id] = fake_caller_id
    app.dependency_overrides[get_authenticated_caller] = lambda: AuthenticatedCaller(
        id="ops-1", roles=("event_operations_manager",)
    )
    return TestClient(app)


def headers(caller_id: str = "ops-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {caller_id}"}


def submit_event_request(repository: FakeEventRequestRepository) -> str:
    row = repository.create(
        {
            "organiser_id": "organiser-1",
            "status": "Submitted",
            "event_name": "Community Dinner",
        }
    )
    return row["id"]


# Purpose: Confirms an Operations Manager can assign a Coordinator to a submitted request.
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


# Purpose: Confirms assignment alone doesn't change the event request's status (AC:
# "remains Submitted") — assignment and status are owned by separate tables/services.
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


# Purpose: 404s rather than assigning a Coordinator to a request that doesn't exist.
def test_assign_coordinator_to_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )

    assert response.status_code == 404


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


# Purpose: 404s when no Coordinator has been assigned yet, distinct from a missing request.
def test_get_coordinator_when_none_assigned() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        response = client.get(
            f"/event-requests/{event_request_id}/coordinator",
            headers=headers(),
        )

    assert response.status_code == 404


# Purpose: Ensures both endpoints reject requests without a verified session
# (exercising the real authentication dependencies, not the test overrides).
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


# Purpose: Refuses assignment for an authenticated caller who isn't an Operations Manager
# (exercising the real get_operations_manager_id against all assigned roles).
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


# Purpose: Allows assignment when one of the caller's roles is Event Operations Manager.
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


# Purpose: Gives the Operations Manager the queue of Submitted requests that still
# need a Coordinator.
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


# Purpose: Confirms the queue is closed to callers who aren't an Operations Manager.
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


# Purpose: Assignment details must not leak to authenticated users without a
# request relationship, while any qualifying role in a multi-role account works.
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
