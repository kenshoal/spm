from copy import deepcopy
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
    make_client,
)

from app.config import get_settings
from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
)
from app.main import create_app

COMPLETE_REQUEST = {
    "event_name": "Updated Community Dinner",
    "purpose": "Bring neighbours together",
    "description": "An amended event plan.",
    "proposed_date_times": ["2026-11-20T10:00:00+08:00"],
    "expected_attendance": 50,
    "venue_requirements": "Accessible hall",
    "accessibility_needs": "Step-free access",
    "equipment_requirements": "No technical kit required",
    "registration_needs": "Online registration",
}


def under_review_fixture() -> tuple[
    TestClient, FakeEventRequestRepository, str
]:
    events = FakeEventRequestRepository()
    assignments = FakeCoordinatorAssignmentRepository(events)
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = "Under Review"
    assign_coordinator(assignments, event_request_id, "coord-1")
    return make_client(events, assignments), events, event_request_id


@pytest.mark.parametrize(
    ("decision", "reason"),
    [
        ("Approved", None),
        ("Changes Requested", "Please clarify the accessibility plan."),
        ("Rejected", "The proposed event is outside the programme scope."),
    ],
)
# Purpose: Each supported review outcome updates the request and retains one decision.
# SCRUM-17 AC2-P1, AC2-P2, AC2-P3 (partition): each supported decision outcome —
# approve, clarify, reject — settles an Under Review request and retains exactly
# one decision row carrying the coordinator's id and reason.
def test_assigned_coordinator_can_record_review_decision(
    decision: str, reason: str | None
) -> None:
    client, events, event_request_id = under_review_fixture()

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": decision, "reason": reason},
        )

    assert response.status_code == 200
    assert response.json()["status"] == decision
    assert events.rows[event_request_id]["status"] == decision
    assert len(events.review_decision_rows) == 1
    assert events.review_decision_rows[0]["event_request_id"] == event_request_id
    assert events.review_decision_rows[0]["coordinator_id"] == "coord-1"
    assert events.review_decision_rows[0]["decision_status"] == decision
    assert events.review_decision_rows[0]["reason"] == reason


@pytest.mark.parametrize("decision", ["Changes Requested", "Rejected"])
# Purpose: A return or rejection cannot leave the organiser without an explanation.
# SCRUM-17 AC3-N1 (negative): a blank reason for clarify or reject is refused
# (422) and the request stays Under Review with no decision row.
def test_return_or_rejection_requires_reason(decision: str) -> None:
    client, events, event_request_id = under_review_fixture()

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": decision, "reason": "   "},
        )

    assert response.status_code == 422
    assert events.rows[event_request_id]["status"] == "Under Review"
    assert events.review_decision_rows == []


# Purpose: A coordinator who is not currently assigned cannot decide the request.
# SCRUM-17 AC2-N1 (negative): a coordinator other than the current assignee is
# refused (403) and neither the status nor the history changes.
def test_unassigned_coordinator_cannot_record_decision() -> None:
    client, events, event_request_id = under_review_fixture()

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-2"),
            json={"decision": "Approved"},
        )

    assert response.status_code == 403
    assert events.rows[event_request_id]["status"] == "Under Review"
    assert events.review_decision_rows == []


# Purpose: Reassignment immediately removes the former coordinator's authority to decide.
# SCRUM-17 AC2-N2 (negative): reassignment immediately strips the former
# coordinator's authority to decide (403), leaving the review untouched.
def test_reassigned_away_coordinator_cannot_record_decision() -> None:
    events = FakeEventRequestRepository()
    assignments = FakeCoordinatorAssignmentRepository(events)
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = "Under Review"
    assign_coordinator(assignments, event_request_id, "coord-1")
    assign_coordinator(assignments, event_request_id, "coord-2")

    with make_client(events, assignments) as client:
        response = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": "Approved"},
        )

    assert response.status_code == 403
    assert events.rows[event_request_id]["status"] == "Under Review"
    assert events.review_decision_rows == []


@pytest.mark.parametrize("status", ["Submitted", "Approved", "Rejected"])
# Purpose: Stale or repeated review actions cannot overwrite a settled workflow state.
# SCRUM-17 AC2-P4, AC2-P5, AC2-P6 (partition): a decision is accepted only
# while the request is Under Review — a stale or repeated decision conflicts
# (409) and writes no second outcome.
def test_decision_requires_under_review_status(status: str) -> None:
    client, events, event_request_id = under_review_fixture()
    events.rows[event_request_id]["status"] = status

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": "Approved"},
        )

    assert response.status_code == 409
    assert events.rows[event_request_id]["status"] == status
    assert events.review_decision_rows == []


# Purpose: Arbitrary lifecycle statuses cannot be smuggled through the decision endpoint.
# SCRUM-17 AC2-N3 (negative): a lifecycle value outside the three review
# outcomes cannot be smuggled through the decision endpoint (422) and nothing
# is written.
def test_decision_rejects_status_outside_review_outcomes() -> None:
    client, events, event_request_id = under_review_fixture()

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": "Completed", "reason": "skip ahead"},
        )

    assert response.status_code == 422
    assert events.rows[event_request_id]["status"] == "Under Review"
    assert events.review_decision_rows == []


# Purpose: A missing request returns 404 without creating an orphan decision record.
# SCRUM-17 AC2-N4 (negative): an unknown request id returns 404 without
# creating an orphan decision record.
def test_decision_for_missing_request_returns_not_found() -> None:
    events = FakeEventRequestRepository()
    with make_client(events) as client:
        response = client.post(
            "/event-requests/00000000-0000-0000-0000-000000000001/decision",
            headers=headers("coord-1"),
            json={"decision": "Approved"},
        )

    assert response.status_code == 404
    assert events.review_decision_rows == []


@pytest.mark.parametrize(
    ("caller", "expected_status"),
    [
        (AuthenticatedCaller("organiser-1", ("event_organiser",)), 200),
        (AuthenticatedCaller("coord-1", ("event_coordinator",)), 200),
        (AuthenticatedCaller("organiser-2", ("event_organiser",)), 404),
        (AuthenticatedCaller("coord-2", ("event_coordinator",)), 404),
        (AuthenticatedCaller("ops-1", ("event_operations_manager",)), 403),
    ],
)
# Purpose: Review reasons are visible only through the event relationship that grants access.
# SCRUM-17 AC3-P1, AC3-P2, AC3-P3, AC3-P4, AC3-P5 (partition): retained review
# decisions are readable only through the request relationship — the owner and
# the assigned coordinator see the outcome and reason, another organiser or
# coordinator gets 404 and an unrelated role 403.
def test_decision_history_visibility_follows_request_access(
    caller: AuthenticatedCaller, expected_status: int
) -> None:
    events = FakeEventRequestRepository()
    assignments = FakeCoordinatorAssignmentRepository(events)
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = "Under Review"
    assign_coordinator(assignments, event_request_id, "coord-1")
    events.decide_by_coordinator(
        event_request_id,
        "coord-1",
        "Changes Requested",
        "Clarify the equipment plan.",
    )
    app = create_app(events, assignments)
    app.dependency_overrides[get_authenticated_caller] = lambda: caller

    with TestClient(app) as client:
        response = client.get(f"/event-requests/{event_request_id}/decisions")

    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json()[0]["decision_status"] == "Changes Requested"
        assert response.json()[0]["reason"] == "Clarify the equipment plan."


# Purpose: The organiser answers the retained clarification without mutating the submitted request.
# SCRUM-17 AC4-H1 (happy): the owning organiser answers the retained
# clarification, the response is kept, and the submitted fields and status stay
# unchanged.
def test_organiser_responds_without_editing_submitted_request() -> None:
    client, events, event_request_id = under_review_fixture()
    original_name = events.rows[event_request_id]["event_name"]
    events.decide_by_coordinator(
        event_request_id, "coord-1", "Changes Requested", "Clarify equipment."
    )

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-1"),
            json={"response": "A wireless microphone is required."},
        )

    assert response.status_code == 200
    assert response.json()["organiser_response"] == "A wireless microphone is required."
    assert events.rows[event_request_id]["status"] == "Changes Requested"
    assert events.rows[event_request_id]["event_name"] == original_name


@pytest.mark.parametrize("status", ["Draft", "Submitted", "Under Review", "Rejected"])
# Purpose: Clarification responses are accepted only for the active returned review.
# SCRUM-17 AC4-P1, AC4-P2, AC4-P3, AC4-P4 (partition): a clarification response
# is accepted only while the active outcome is Changes Requested; every other
# status conflicts (409) and the request is unchanged.
def test_clarification_response_requires_changes_requested_status(status: str) -> None:
    events = FakeEventRequestRepository()
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = status

    with make_client(events) as client:
        response = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-1"),
            json={"response": "More details."},
        )

    assert response.status_code == 409
    assert events.rows[event_request_id]["status"] == status


# Purpose: Another organiser cannot answer a clarification on someone else's request.
# SCRUM-17 AC4-N1 (negative): another organiser cannot answer someone else's
# clarification (404) and the clarification stays unanswered.
def test_other_organiser_cannot_respond_to_clarification() -> None:
    client, events, event_request_id = under_review_fixture()
    events.decide_by_coordinator(
        event_request_id, "coord-1", "Changes Requested", "Clarify equipment."
    )

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-2"),
            json={"response": "More details."},
        )

    assert response.status_code == 404
    assert events.review_decision_rows[0]["organiser_response"] is None


# Purpose: The assigned coordinator resumes review only after the organiser responds.
# SCRUM-17 AC4-H2 (happy): after the organiser responds, the assigned
# coordinator resumes the review and the request returns to Under Review.
def test_assigned_coordinator_resumes_after_clarification_response() -> None:
    client, events, event_request_id = under_review_fixture()
    events.decide_by_coordinator(
        event_request_id, "coord-1", "Changes Requested", "Clarify equipment."
    )
    events.respond_to_clarification(event_request_id, "organiser-1", "Microphone needed.")

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/resume-review",
            headers=headers("coord-1"),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "Under Review"


# Purpose: A coordinator cannot skip the organiser's clarification response.
# SCRUM-17 AC4-N2 (negative): the coordinator cannot skip the organiser's
# response — resume conflicts (409) and the request stays Changes Requested.
def test_coordinator_cannot_resume_before_organiser_response() -> None:
    client, events, event_request_id = under_review_fixture()
    events.decide_by_coordinator(
        event_request_id, "coord-1", "Changes Requested", "Clarify equipment."
    )

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/resume-review",
            headers=headers("coord-1"),
        )

    assert response.status_code == 409
    assert events.rows[event_request_id]["status"] == "Changes Requested"


# Purpose: A later approval must not overwrite the clarification exchange that informed it.
# SCRUM-17 AC3-H1 (happy): the clarify → respond → resume → approve sequence
# appends a second decision without overwriting the clarification exchange that
# informed it.
def test_review_history_retains_clarification_after_approval() -> None:
    client, events, event_request_id = under_review_fixture()

    with client:
        clarified = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": "Changes Requested", "reason": "Clarify equipment."},
        )
        answered = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-1"),
            json={"response": "Two wireless microphones are required."},
        )
        resumed = client.post(
            f"/event-requests/{event_request_id}/resume-review",
            headers=headers("coord-1"),
        )
        approved = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": "Approved"},
        )

    assert [clarified.status_code, answered.status_code, resumed.status_code, approved.status_code] == [200, 200, 200, 200]
    assert len(events.review_decision_rows) == 2
    clarification, approval = events.review_decision_rows
    assert clarification["decision_status"] == "Changes Requested"
    assert clarification["reason"] == "Clarify equipment."
    assert clarification["organiser_response"] == "Two wireless microphones are required."
    assert approval["decision_status"] == "Approved"
    assert approval["reason"] is None


# Purpose: A blank organiser response cannot turn an unanswered clarification into a completed exchange.
# SCRUM-17 AC4-N3 (negative): a blank response is refused (422) and the
# clarification stays unanswered with no timestamp.
def test_blank_clarification_response_is_rejected_without_mutation() -> None:
    client, events, event_request_id = under_review_fixture()
    events.decide_by_coordinator(
        event_request_id, "coord-1", "Changes Requested", "Clarify equipment."
    )

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-1"),
            json={"response": "   "},
        )

    assert response.status_code == 422
    assert events.rows[event_request_id]["status"] == "Changes Requested"
    assert events.review_decision_rows[0]["organiser_response"] is None
    assert events.review_decision_rows[0]["responded_at"] is None


# Purpose: A repeated response cannot replace the organiser's first retained answer.
# SCRUM-17 AC4-N4 (negative): a repeated response conflicts (409) and cannot
# replace the organiser's first retained answer.
def test_duplicate_clarification_response_preserves_first_answer() -> None:
    client, events, event_request_id = under_review_fixture()
    events.decide_by_coordinator(
        event_request_id, "coord-1", "Changes Requested", "Clarify equipment."
    )

    with client:
        first = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-1"),
            json={"response": "Two microphones are required."},
        )
        retained = deepcopy(events.review_decision_rows[0])
        second = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-1"),
            json={"response": "Replace that with four microphones."},
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert events.rows[event_request_id]["status"] == "Changes Requested"
    assert events.review_decision_rows == [retained]


@pytest.mark.parametrize(("length", "expected_status"), [(2_000, 200), (2_001, 422)])
# Purpose: The decision-reason limit accepts the documented boundary and rejects overflow without writing it.
# SCRUM-17 AC3-B1, AC3-B2 (boundary): a 2,000-character decision reason is
# retained; 2,001 is refused (422) and writes nothing.
def test_decision_reason_length_boundary(length: int, expected_status: int) -> None:
    client, events, event_request_id = under_review_fixture()
    reason = "r" * length

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/decision",
            headers=headers("coord-1"),
            json={"decision": "Changes Requested", "reason": reason},
        )

    assert response.status_code == expected_status
    if expected_status == 200:
        assert events.review_decision_rows[0]["reason"] == reason
    else:
        assert events.rows[event_request_id]["status"] == "Under Review"
        assert events.review_decision_rows == []


@pytest.mark.parametrize(("length", "expected_status"), [(2_000, 200), (2_001, 422)])
# Purpose: The response limit accepts the documented boundary and leaves an overflowing clarification unanswered.
# SCRUM-17 AC4-B1, AC4-B2 (boundary): a 2,000-character response is retained;
# 2,001 is refused (422) and the clarification stays unanswered.
def test_clarification_response_length_boundary(length: int, expected_status: int) -> None:
    client, events, event_request_id = under_review_fixture()
    events.decide_by_coordinator(
        event_request_id, "coord-1", "Changes Requested", "Clarify equipment."
    )
    answer = "a" * length

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/clarification-response",
            headers=headers("organiser-1"),
            json={"response": answer},
        )

    assert response.status_code == expected_status
    assert events.rows[event_request_id]["status"] == "Changes Requested"
    assert events.review_decision_rows[0]["organiser_response"] == (
        answer if expected_status == 200 else None
    )


@pytest.mark.parametrize(
    ("roles", "path", "payload"),
    [
        (["event_organiser"], "/decision", {"decision": "Approved"}),
        (["event_organiser"], "/resume-review", None),
        (["event_coordinator"], "/clarification-response", {"response": "Answer"}),
    ],
)
# Purpose: Each SCRUM-17 mutation is restricted to the actor named by its acceptance criterion.
# SCRUM-17 AC2-X1 (cross-cutting): each review mutation is restricted to the
# actor its criterion names — decision and resume to the assigned coordinator,
# the response to the owning organiser — and a wrong-role call (403) writes
# nothing.
def test_review_mutations_reject_wrong_role(
    monkeypatch: pytest.MonkeyPatch,
    roles: list[str],
    path: str,
    payload: dict[str, str] | None,
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
    get_settings.cache_clear()
    events = FakeEventRequestRepository()
    assignments = FakeCoordinatorAssignmentRepository(events)
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = "Under Review"
    assign_coordinator(assignments, event_request_id, caller_id)
    if path in {"/resume-review", "/clarification-response"}:
        events.decide_by_coordinator(
            event_request_id, caller_id, "Changes Requested", "Clarify equipment."
        )
    if path == "/resume-review":
        events.respond_to_clarification(
            event_request_id, "organiser-1", "Two microphones are required."
        )
    before_status = events.rows[event_request_id]["status"]
    before_history = deepcopy(events.review_decision_rows)

    try:
        with TestClient(create_app(events, assignments)) as client:
            response = client.post(
                f"/event-requests/{event_request_id}{path}",
                headers={"Authorization": "Bearer valid-token"},
                json=payload,
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert events.rows[event_request_id]["status"] == before_status
    assert events.review_decision_rows == before_history


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/decision", {"decision": "Approved"}),
        ("/resume-review", None),
        ("/clarification-response", {"response": "Answer"}),
    ],
)
# Purpose: Missing authentication cannot mutate any SCRUM-17 review state.
# SCRUM-17 AC2-X2 (cross-cutting): a caller with no session is refused (401) on
# every review mutation and the request and its history are untouched.
def test_review_mutations_require_session(
    path: str, payload: dict[str, str] | None
) -> None:
    events = FakeEventRequestRepository()
    assignments = FakeCoordinatorAssignmentRepository(events)
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = "Under Review"
    before = deepcopy(events.rows[event_request_id])

    with TestClient(create_app(events, assignments)) as client:
        response = client.post(
            f"/event-requests/{event_request_id}{path}", json=payload
        )

    assert response.status_code == 401
    assert events.rows[event_request_id] == before
    assert events.review_decision_rows == []


@pytest.mark.parametrize("path", ["review", "resume-review", "decision", "cancellation", "completion"])
# Purpose: Malformed request IDs are rejected at the HTTP boundary instead of reaching Supabase.
# SCRUM-17 AC2-N5 (negative): malformed request ids are rejected at the HTTP
# boundary (422) on every review transition route and never reach Supabase.
def test_transition_routes_validate_event_request_uuid(path: str) -> None:
    with make_client() as client:
        response = client.post(
            f"/event-requests/not-a-uuid/{path}",
            headers=headers("coord-1"),
            json={"decision": "Approved"} if path == "decision" else None,
        )

    assert response.status_code == 422
