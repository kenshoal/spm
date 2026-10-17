"""SCRUM-62 AC2 and AC5: new requests wait for the Event Coordinator Lead and are
never assigned automatically; a coordinator can act on, or even see, only their
own events. Both rules already held; these tests pin them down."""
from uuid import uuid4

import httpx
import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    complete_payload,
)
from test_event_transition_controller import headers, make_assigned_client

from app.controllers.coordinator_assignment_controller import (
    get_operations_manager_id,
)
from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
    get_coordinator_id,
    get_organiser_id,
)
from app.main import create_app


def _caller_from_header(authorization: str = Header()) -> AuthenticatedCaller:
    """Role by name prefix: ops-* is the Lead, coord-* a coordinator."""
    caller_id = authorization.removeprefix("Bearer ")
    if caller_id.startswith("ops-"):
        return AuthenticatedCaller(id=caller_id, roles=("event_operations_manager",))
    if caller_id.startswith("coord-"):
        return AuthenticatedCaller(id=caller_id, roles=("event_coordinator",))
    return AuthenticatedCaller(id=caller_id, roles=("event_organiser",))


def _id_from_header(authorization: str = Header()) -> str:
    return authorization.removeprefix("Bearer ")


def make_lead_client() -> tuple[
    TestClient, FakeEventRequestRepository, FakeCoordinatorAssignmentRepository
]:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    app = create_app(event_requests, coordinators)
    app.dependency_overrides[get_organiser_id] = _id_from_header
    app.dependency_overrides[get_coordinator_id] = _id_from_header
    app.dependency_overrides[get_operations_manager_id] = _id_from_header
    app.dependency_overrides[get_authenticated_caller] = _caller_from_header
    return TestClient(app), event_requests, coordinators


def submit_as_organiser(client: TestClient) -> str:
    created = client.post(
        "/event-requests",
        headers=headers("organiser-1"),
        json={"event_name": "Initial title"},
    ).json()
    submitted = client.post(
        f"/event-requests/{created['id']}/submit",
        headers=headers("organiser-1"),
        json=complete_payload(),
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "Submitted"
    return created["id"]


# AC2-H1 (happy): a submitted request waits in the Lead's queue and is assigned to no one
def test_submitted_request_waits_in_the_lead_queue_unassigned() -> None:
    client, _event_requests, coordinators = make_lead_client()
    with client:
        event_request_id = submit_as_organiser(client)
        queue = client.get(
            "/event-requests/awaiting-assignment", headers=headers("ops-1")
        )

    assert queue.status_code == 200
    assert [request["id"] for request in queue.json()] == [event_request_id]
    assert coordinators.rows == []


# AC2-N1 (negative): no coordinator's own queue contains a request that was just submitted
@pytest.mark.parametrize("coordinator_id", ["coord-1", "coord-2"])
def test_submitted_request_is_in_no_coordinators_queue(coordinator_id: str) -> None:
    client, _event_requests, coordinators = make_lead_client()
    with client:
        submit_as_organiser(client)
        mine = client.get(
            "/event-requests/assigned-to-me", headers=headers(coordinator_id)
        )

    assert mine.status_code == 200
    assert mine.json() == []
    assert coordinators.rows == []


# (path, status the action needs so a refusal can only be about ownership, body)
COORDINATOR_ACTIONS = [
    ("review", "Submitted", None),
    ("resume-review", "Changes Requested", None),
    ("decision", "Under Review", {"decision": "Approved", "reason": None}),
    ("planning", "Approved", None),
    ("cancellation", "Planning", None),
    ("completion", "Confirmed", None),
]


@pytest.mark.parametrize(
    ("path", "needed_status", "body"),
    COORDINATOR_ACTIONS,
    ids=[f"AC5-N{k}" for k in range(1, len(COORDINATOR_ACTIONS) + 1)],
)
# AC5-N1..N6 (negative): a coordinator who is not assigned is refused on every coordinator-owned action and the status stays put
def test_unassigned_coordinator_is_refused_on_every_action(
    path: str, needed_status: str, body: dict[str, object] | None
) -> None:
    client, event_requests, event_request_id = make_assigned_client(
        coordinator_id="coord-1", status=needed_status
    )
    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/{path}",
            headers=headers("coord-2"),
            json=body,
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == needed_status


# AC5-N7 (negative): a coordinator who is not assigned cannot see the event, and the 404 does not reveal it exists
def test_unassigned_coordinator_cannot_see_the_event() -> None:
    client, _event_requests, event_request_id = make_assigned_client(
        coordinator_id="coord-1", status="Planning"
    )
    client.app.dependency_overrides[get_authenticated_caller] = _caller_from_header
    with client:
        response = client.get(
            f"/event-requests/{event_request_id}", headers=headers("coord-2")
        )

    assert response.status_code == 404
    assert "event_name" not in response.json()


# AC5-H1 (happy): the assigned coordinator can still see the event, so the refusals above are about ownership
def test_assigned_coordinator_can_see_the_event() -> None:
    client, _event_requests, event_request_id = make_assigned_client(
        coordinator_id="coord-1", status="Planning"
    )
    client.app.dependency_overrides[get_authenticated_caller] = _caller_from_header
    with client:
        response = client.get(
            f"/event-requests/{event_request_id}", headers=headers("coord-1")
        )

    assert response.status_code == 200
    assert response.json()["id"] == event_request_id


# AC1-H4 (happy): a caller who is not the Lead is told that only the Event Coordinator Lead can assign, not the old role name
def test_refusal_names_the_event_coordinator_lead(
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
    assert response.json()["detail"] == (
        "Only an Event Coordinator Lead can assign a Coordinator"
    )
