from fastapi import Header
from fastapi.testclient import TestClient
from test_coordinator_assignment_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)

from app.controllers.event_request_controller import get_organiser_id
from app.main import create_app


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


# Purpose: The assigned Coordinator starting review moves Submitted -> Under Review.
def test_assigned_coordinator_can_start_review() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
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
    coordinators = FakeCoordinatorAssignmentRepository()
    with make_client(event_requests, coordinators):
        event_request_id = submit_event_request(event_requests)
        assign_coordinator(coordinators, event_request_id, "coord-1")

    assert event_requests.rows[event_request_id]["status"] == "Submitted"


# Purpose: Refuses review from anyone other than the assigned Coordinator.
def test_start_review_refused_for_non_assigned_caller() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
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
    coordinators = FakeCoordinatorAssignmentRepository()
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
    coordinators = FakeCoordinatorAssignmentRepository()
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


# Purpose: Ensures the endpoint rejects requests without a verified session.
def test_start_review_requires_bearer_session() -> None:
    app = create_app(FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository())
    with TestClient(app) as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/review"
        )

    assert response.status_code == 401
