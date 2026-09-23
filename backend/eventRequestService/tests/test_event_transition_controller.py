from uuid import uuid4

import httpx
import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_event_request_controller import (
    CANCEL_SOURCE_STATUSES,
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)

from app.controllers.event_request_controller import (
    get_coordinator_id,
    get_organiser_id,
)
from app.main import create_app


def make_client(
    event_request_repository: FakeEventRequestRepository | None = None,
    coordinator_repository: FakeCoordinatorAssignmentRepository | None = None,
) -> TestClient:
    event_request_repository = (
        event_request_repository or FakeEventRequestRepository()
    )
    coordinator_repository = (
        coordinator_repository
        # Linked so the fake's atomic transition sees the assignments.
        or FakeCoordinatorAssignmentRepository(event_request_repository)
    )
    app = create_app(event_request_repository, coordinator_repository)

    def fake_caller_id(authorization: str = Header()) -> str:
        return authorization.removeprefix("Bearer ")

    app.dependency_overrides[get_organiser_id] = fake_caller_id
    app.dependency_overrides[get_coordinator_id] = fake_caller_id
    return TestClient(app)


def headers(caller_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {caller_id}"}


def assign_coordinator(
    coordinator_repository: FakeCoordinatorAssignmentRepository,
    event_request_id: str,
    coordinator_id: str,
) -> None:
    coordinator_repository.create(
        {
            "event_request_id": event_request_id,
            "coordinator_id": coordinator_id,
            "assigned_by": "ops-1",
        }
    )


def make_assigned_client(
    coordinator_id: str = "coord-1",
    status: str = "Submitted",
) -> tuple[TestClient, FakeEventRequestRepository, str]:
    """Client wired for transition tests: one submitted request assigned to
    coordinator_id, with its status pre-set (assignments can't be created for
    statuses no story writes yet, so seeds stand in for ops/venue flows)."""
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    event_request_id = submit_event_request(event_requests)
    event_requests.rows[event_request_id]["status"] = status
    assign_coordinator(coordinators, event_request_id, coordinator_id)
    return make_client(event_requests, coordinators), event_requests, event_request_id


# Purpose: The assigned Coordinator starting review moves Submitted -> Under Review.
def test_assigned_coordinator_can_start_review() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        assign_coordinator(coordinators, event_request_id, "coord-1")

        response = client.post(
            f"/event-requests/{event_request_id}/review",
            headers=headers("coord-1"),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "Under Review"


# Purpose: Assignment alone must not move status — only starting review does.
def test_assignment_alone_does_not_start_review() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators):
        event_request_id = submit_event_request(event_requests)
        assign_coordinator(coordinators, event_request_id, "coord-1")

    assert event_requests.rows[event_request_id]["status"] == "Submitted"


# Purpose: Refuses review from anyone other than the assigned Coordinator.
def test_start_review_refused_for_non_assigned_caller() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        assign_coordinator(coordinators, event_request_id, "coord-1")

        response = client.post(
            f"/event-requests/{event_request_id}/review",
            headers=headers("coord-2"),
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Submitted"


# Purpose: Refuses review when no Coordinator has been assigned at all.
def test_start_review_refused_when_unassigned() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)

        response = client.post(
            f"/event-requests/{event_request_id}/review",
            headers=headers("coord-1"),
        )

    assert response.status_code == 403


# Purpose: Refuses starting review on a request that's still a Draft.
def test_start_review_refused_before_submission() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators) as client:
        created = client.post(
            "/event-requests",
            headers=headers("organiser-1"),
            json={"event_name": "Still a draft"},
        ).json()
        assign_coordinator(coordinators, created["id"], "coord-1")

        response = client.post(
            f"/event-requests/{created['id']}/review",
            headers=headers("coord-1"),
        )

    assert response.status_code == 409


# Purpose: Refuses starting review a second time once already Under Review.
def test_start_review_refused_once_already_under_review() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    with make_client(event_requests, coordinators) as client:
        event_request_id = submit_event_request(event_requests)
        assign_coordinator(coordinators, event_request_id, "coord-1")
        client.post(
            f"/event-requests/{event_request_id}/review",
            headers=headers("coord-1"),
        )

        response = client.post(
            f"/event-requests/{event_request_id}/review",
            headers=headers("coord-1"),
        )

    assert response.status_code == 409


# Purpose: 404s rather than starting review on a request that doesn't exist.
def test_start_review_for_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/review",
            headers=headers("coord-1"),
        )

    assert response.status_code == 404


def test_start_review_requires_event_coordinator_role(
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
                "role": "attendee",
                "roles": ["attendee"],
            },
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    try:
        app = create_app(event_requests, coordinators)
        event_request_id = submit_event_request(event_requests)
        assign_coordinator(coordinators, event_request_id, caller_id)
        with TestClient(app) as client:
            response = client.post(
                f"/event-requests/{event_request_id}/review",
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


@pytest.mark.parametrize("from_status", sorted(CANCEL_SOURCE_STATUSES))
# Purpose: The assigned Coordinator can cancel a request from any non-terminal status.
def test_assigned_coordinator_can_cancel_from_every_non_terminal_status(
    from_status: str,
) -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status=from_status
    )
    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/cancellation",
            headers=headers("coord-1"),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "Cancelled"
    assert event_requests.rows[event_request_id]["status"] == "Cancelled"


# Purpose: Cancelling is refused once the request has reached a terminal status.
@pytest.mark.parametrize("from_status", ["Completed", "Cancelled", "Rejected"])
def test_cancel_refused_from_terminal_status(from_status: str) -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status=from_status
    )
    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/cancellation",
            headers=headers("coord-1"),
        )

    assert response.status_code == 409
    assert event_requests.rows[event_request_id]["status"] == from_status


# Purpose: Cancelling a Draft is impossible — drafts carry no coordinator assignment.
def test_cancel_refused_for_draft_without_assignment() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    row = event_requests.create(
        {
            "organiser_id": "organiser-1",
            "status": "Draft",
            "event_name": "Still a draft",
        }
    )
    with make_client(event_requests, coordinators) as client:
        response = client.post(
            f"/event-requests/{row['id']}/cancellation",
            headers=headers("coord-1"),
        )

    assert response.status_code == 403
    assert event_requests.rows[row["id"]]["status"] == "Draft"


# Purpose: Only the latest-assigned Coordinator may cancel — a reassigned-away
# coordinator's cancellation is refused without mutating the request.
def test_cancel_refused_for_reassigned_away_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    event_request_id = submit_event_request(event_requests)
    assign_coordinator(coordinators, event_request_id, "coord-1")
    assign_coordinator(coordinators, event_request_id, "coord-2")

    with make_client(event_requests, coordinators) as client:
        response = client.post(
            f"/event-requests/{event_request_id}/cancellation",
            headers=headers("coord-1"),
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Submitted"


# Purpose: Cancelling is refused when no Coordinator has been assigned at all.
def test_cancel_refused_when_unassigned() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)

        response = client.post(
            f"/event-requests/{event_request_id}/cancellation",
            headers=headers("coord-1"),
        )

    assert response.status_code == 403


# Purpose: Cancelling a request that doesn't exist 404s rather than guessing.
def test_cancel_for_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/cancellation",
            headers=headers("coord-1"),
        )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    ["/cancellation", "/completion", "/review"],
)
# Purpose: Transition endpoints reject requests without a verified session.
def test_transitions_require_bearer_session(path: str) -> None:
    app = create_app(FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository())
    with TestClient(app) as client:
        response = client.post(
            f"/event-requests/00000000-0000-0000-0000-000000000001{path}"
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("roles", "path"),
    [
        (["event_organiser"], "/cancellation"),
        (["event_operations_manager"], "/cancellation"),
        (["event_organiser"], "/completion"),
        (["event_operations_manager"], "/completion"),
    ],
)
# Purpose: Only coordinators may call the transition endpoints — organisers and
# operations managers are refused even on requests they can read.
def test_transitions_require_coordinator_role(
    monkeypatch: pytest.MonkeyPatch,
    roles: list[str],
    path: str,
) -> None:
    caller_id = str(uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"id": caller_id, "role": roles[0], "roles": roles},
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    try:
        app = create_app(event_requests, coordinators)
        event_request_id = submit_event_request(event_requests)
        assign_coordinator(coordinators, event_request_id, caller_id)
        with TestClient(app) as client:
            response = client.post(
                f"/event-requests/{event_request_id}{path}",
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


# Purpose: The assigned Coordinator completing a Confirmed request marks it Completed.
def test_assigned_coordinator_completes_confirmed_request() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status="Confirmed"
    )
    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/completion",
            headers=headers("coord-1"),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "Completed"
    assert event_requests.rows[event_request_id]["status"] == "Completed"


@pytest.mark.parametrize(
    "from_status", ["Draft", "Submitted", "Under Review", "Cancelled"]
)
# Purpose: Completion only applies to Confirmed — every other status refuses untouched.
def test_complete_refused_from_other_than_confirmed(from_status: str) -> None:
    if from_status == "Draft":
        event_requests = FakeEventRequestRepository()
        coordinators = FakeCoordinatorAssignmentRepository(event_requests)
        created = event_requests.create(
            {
                "organiser_id": "organiser-1",
                "status": "Draft",
                "event_name": "Still a draft",
            }
        )
        event_request_id = created["id"]
        client = make_client(event_requests, coordinators)
    else:
        client, event_requests, event_request_id = make_assigned_client(
            status=from_status
        )

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/completion",
            headers=headers("coord-1"),
        )

    assert response.status_code == (403 if from_status == "Draft" else 409)
    assert event_requests.rows[event_request_id]["status"] == from_status


# Purpose: Completion is refused for a coordinator other than the one assigned.
def test_complete_refused_for_non_assigned_coordinator() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        coordinator_id="coord-2",
        status="Confirmed",
    )
    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/completion",
            headers=headers("coord-1"),
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Confirmed"


# Purpose: Completing is refused when no Coordinator has been assigned at all.
def test_complete_refused_when_unassigned() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        event_request_id = submit_event_request(event_requests)
        event_requests.rows[event_request_id]["status"] = "Confirmed"

        response = client.post(
            f"/event-requests/{event_request_id}/completion",
            headers=headers("coord-1"),
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Confirmed"


# Purpose: Completing a request that doesn't exist 404s rather than guessing.
def test_complete_for_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/completion",
            headers=headers("coord-1"),
        )

    assert response.status_code == 404


# Purpose: A stale transition (status moved after the coordinator loaded the page)
# is refused with 409 and leaves the row at its current status.
def test_stale_review_refused_after_cancellation_without_second_mutation() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status="Submitted"
    )
    with client:
        cancelled = client.post(
            f"/event-requests/{event_request_id}/cancellation",
            headers=headers("coord-1"),
        )
        review = client.post(
            f"/event-requests/{event_request_id}/review",
            headers=headers("coord-1"),
        )

    assert cancelled.status_code == 200
    assert review.status_code == 409
    assert event_requests.rows[event_request_id]["status"] == "Cancelled"
