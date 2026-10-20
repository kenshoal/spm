"""SCRUM-58 AC2, AC3a and AC4: the assigned coordinator sends a ready Planning
event to Safety Review; an unready one is refused with what is outstanding.
Which bookings and reservations count as ready is decided by the database
function and proven in verify_safety_review_readiness.sql, not here."""
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

OUTSTANDING = [
    {"kind": "no_venue_booking"},
    {
        "kind": "venue_booking_pending",
        "booking_id": "b-1",
        "venue_name": "Hall F",
    },
    {
        "kind": "equipment_not_reserved",
        "requirement_id": "r-1",
        "equipment_type": "Microphone",
        "required": 3,
        "reserved": 2,
    },
]


def safety_review_path(event_request_id: str) -> str:
    return f"/event-requests/{event_request_id}/safety-review"


# AC2-H2 (happy): a ready Planning event moves to Safety Review
def test_assigned_coordinator_sends_ready_event_to_safety_review() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status="Planning"
    )
    with client:
        response = client.post(
            safety_review_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == event_request_id
    assert body["status"] == "Safety Review"
    assert event_requests.rows[event_request_id]["status"] == "Safety Review"


# AC3-N5 (negative): an unready event is refused with every outstanding item, each in plain words
def test_send_refused_with_outstanding_items_when_not_ready() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status="Planning"
    )
    event_requests.safety_review_outstanding[event_request_id] = OUTSTANDING
    with client:
        response = client.post(
            safety_review_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": f"Event request {event_request_id} is not ready for safety review",
        "outstanding": [
            {**OUTSTANDING[0], "message": "No venue is booked for this event"},
            {
                **OUTSTANDING[1],
                "message": "The booking for Hall F is still waiting for a decision",
            },
            {**OUTSTANDING[2], "message": "Microphone: 2 of 3 reserved"},
        ],
    }
    assert event_requests.rows[event_request_id]["status"] == "Planning"


@pytest.mark.parametrize(
    "from_status",
    [
        "Submitted",
        "Under Review",
        "Changes Requested",
        "Approved",
        "Rejected",
        "Safety Review",
        "Confirmed",
        "Completed",
        "Cancelled",
    ],
    ids=[f"AC2-P{k}" for k in range(3, 12)],
)
# AC2-P3..P11 (partition): only Planning can be sent; every other status is refused unchanged
def test_send_refused_from_other_than_planning(from_status: str) -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status=from_status
    )
    with client:
        response = client.post(
            safety_review_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 409
    assert "outstanding" not in response.json()
    assert event_requests.rows[event_request_id]["status"] == from_status


# AC2-N3 (negative): a request that does not exist is a 404 from the service, not the router
def test_send_for_missing_request() -> None:
    with make_client() as client:
        response = client.post(
            safety_review_path("00000000-0000-0000-0000-000000000001"),
            headers=headers("coord-1"),
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Event request 00000000-0000-0000-0000-000000000001 was not found"
    }


# AC4-N12 (negative): another coordinator is refused with 403 and learns nothing about readiness
def test_send_refused_for_non_assigned_coordinator() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        coordinator_id="coord-2", status="Planning"
    )
    event_requests.safety_review_outstanding[event_request_id] = OUTSTANDING
    with client:
        response = client.post(
            safety_review_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 403
    assert "outstanding" not in response.json()
    assert event_requests.rows[event_request_id]["status"] == "Planning"


# AC4-N13 (negative): a coordinator reassigned away is refused — the latest assignment wins
def test_send_refused_for_reassigned_away_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(event_requests)
    event_request_id = submit_event_request(event_requests)
    event_requests.rows[event_request_id]["status"] = "Planning"
    assign_coordinator(coordinators, event_request_id, "coord-1")
    assign_coordinator(coordinators, event_request_id, "coord-2")

    with make_client(event_requests, coordinators) as client:
        response = client.post(
            safety_review_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Planning"


# AC4-N14 (negative): with no coordinator assigned at all, sending is refused
def test_send_refused_when_unassigned() -> None:
    event_requests = FakeEventRequestRepository()
    event_request_id = submit_event_request(event_requests)
    event_requests.rows[event_request_id]["status"] = "Planning"

    with make_client(event_requests) as client:
        response = client.post(
            safety_review_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Planning"


# AC4-N15 (negative): a caller with no session is refused before anything is read
def test_send_requires_bearer_session() -> None:
    app = create_app(
        FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository()
    )
    with TestClient(app) as client:
        response = client.post(
            safety_review_path("00000000-0000-0000-0000-000000000001")
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "role",
    ["event_organiser", "event_operations_manager", "safety_officer"],
    ids=["AC4-N16", "AC4-N17", "AC4-N18"],
)
# AC4-N16..N18 (negative): non-coordinator roles, including the Safety Officer, cannot send
def test_send_requires_coordinator_role(
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
        event_requests.rows[event_request_id]["status"] = "Planning"
        assign_coordinator(coordinators, event_request_id, caller_id)
        with TestClient(app) as client:
            response = client.post(
                safety_review_path(event_request_id),
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert event_requests.rows[event_request_id]["status"] == "Planning"


# AC3-N10 (negative): an outstanding SCRUM-64 review is listed with its reason in plain words
def test_send_refused_lists_arrangement_review_with_its_reason() -> None:
    client, event_requests, event_request_id = make_assigned_client(
        status="Planning"
    )
    review = {
        "kind": "arrangement_needs_review",
        "review_id": "rv-1",
        "arrangement": "venue_booking",
        "arrangement_id": "b-2",
        "reason": "Attendance changed",
    }
    event_requests.safety_review_outstanding[event_request_id] = [review]
    with client:
        response = client.post(
            safety_review_path(event_request_id), headers=headers("coord-1")
        )

    assert response.status_code == 409
    assert response.json()["outstanding"] == [
        {**review, "message": "Still marked for review: Attendance changed"}
    ]
    assert event_requests.rows[event_request_id]["status"] == "Planning"


# AC3-X6 (cross-cutting): SCRUM-60's approval refusal words readiness items the same way as the handover
def test_approval_refusal_words_readiness_and_review_items_like_handover() -> None:
    from app.services.event_transition_service import SafetyApprovalBlockedError

    items = [
        {"kind": "no_venue_booking"},
        {
            "kind": "equipment_not_reserved",
            "requirement_id": "r-1",
            "equipment_type": "Microphone",
            "required": 3,
            "reserved": 2,
        },
        {"kind": "arrangement_needs_review", "review_id": "rv-1", "reason": "Exit moved"},
    ]

    error = SafetyApprovalBlockedError("event-1", items)

    assert [item["message"] for item in error.outstanding] == [
        "No venue is booked for this event",
        "Microphone: 2 of 3 reserved",
        "Still marked for review: Exit moved",
    ]
