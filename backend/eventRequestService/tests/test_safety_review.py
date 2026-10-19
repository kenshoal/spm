"""SCRUM-60 increment 2: the Safety Officer's decision and the coordinator's view of it."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)
from test_event_transition_controller import assign_coordinator

from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
)
from app.main import create_app
from app.services.event_transition_service import EventTransitionService

OFFICER = "safety-1"
COORDINATOR = "coord-1"
REASON = "Exit routes for 300 people are not shown for Hall B."
TARGETS = [
    {"arrangement": "venue_booking", "id": "11111111-1111-4111-8111-111111111111"},
    {"arrangement": "equipment_reservation", "id": "22222222-2222-4222-8222-222222222222"},
]

ROLES = {
    OFFICER: ("safety_officer",),
    COORDINATOR: ("event_coordinator",),
    "coord-2": ("event_coordinator",),
    "organiser-1": ("event_organiser",),
}


def override(authorization: str | None = Header(default=None)) -> AuthenticatedCaller:
    """Stand-in for authService: the bearer token is the caller id."""
    if not authorization:
        raise HTTPException(401, "Authentication required")
    caller_id = authorization.removeprefix("Bearer ")
    return AuthenticatedCaller(caller_id, ROLES[caller_id])


class SpyNotificationClient:
    def __init__(self) -> None:
        self.safety_changes: list[dict[str, Any]] = []

    def notify_safety_changes_requested(self, **kwargs: Any) -> None:
        self.safety_changes.append(kwargs)


def safety_fixture(
    status: str = "Safety Review",
) -> tuple[TestClient, FakeEventRequestRepository, str, SpyNotificationClient]:
    events = FakeEventRequestRepository()
    assignments = FakeCoordinatorAssignmentRepository(events)
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = status
    assign_coordinator(assignments, event_request_id, COORDINATOR)
    events.safety_officer_ids.add(OFFICER)
    for target in TARGETS:
        events.arrangements.add((event_request_id, target["arrangement"], target["id"]))

    app = create_app(events, assignments)
    app.dependency_overrides[get_authenticated_caller] = override
    spy = SpyNotificationClient()
    app.state.event_transition_service = EventTransitionService(
        app.state.event_request_service, spy
    )
    return TestClient(app), events, event_request_id, spy


def as_(caller_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {caller_id}"}


def decide(client: TestClient, event_request_id: str, body: dict, caller: str = OFFICER):
    with client:
        return client.post(
            f"/event-requests/{event_request_id}/safety-decision",
            headers=as_(caller) if caller else {},
            json=body,
        )


def assert_unchanged(events: FakeEventRequestRepository, event_request_id: str, status: str = "Safety Review") -> None:
    assert events.rows[event_request_id]["status"] == status
    assert events.safety_review_rows == []


# AC3-H1 (happy): approval confirms the event and records who decided.
def test_safety_officer_approves_event() -> None:
    client, events, event_request_id, spy = safety_fixture()

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 200
    assert response.json()["status"] == "Confirmed"
    assert events.rows[event_request_id]["status"] == "Confirmed"
    [review] = events.safety_review_rows
    assert (review["decision"], review["decided_by"]) == ("approved", OFFICER)
    # AC4b-P1 (partition): approval tells the coordinator nothing; the organiser's
    # "confirmed" notice belongs to SCRUM-36.
    assert spy.safety_changes == []


# AC4a-H1 (happy): asking for changes returns the event to Planning and keeps
# the reason and targets exactly as sent.
# AC4b-H1 (happy): the assigned coordinator is told why.
def test_safety_officer_asks_for_changes() -> None:
    client, events, event_request_id, spy = safety_fixture()

    response = decide(
        client,
        event_request_id,
        {"decision": "changes_requested", "reason": REASON, "targets": TARGETS},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "Planning"
    [review] = events.safety_review_rows
    assert (review["decision"], review["reason"], review["targets"]) == (
        "changes_requested",
        REASON,
        TARGETS,
    )
    assert spy.safety_changes == [
        {
            "event_request_id": event_request_id,
            "coordinator_id": COORDINATOR,
            "reason": REASON,
        }
    ]


# AC4a-P1 (partition): no specific arrangement is affected; still allowed.
def test_changes_with_no_targets_are_allowed() -> None:
    client, events, event_request_id, _ = safety_fixture()

    response = decide(
        client, event_request_id, {"decision": "changes_requested", "reason": REASON}
    )

    assert response.status_code == 200
    assert events.safety_review_rows[0]["targets"] == []


@pytest.mark.parametrize("body", [
    {"decision": "changes_requested"},
    {"decision": "changes_requested", "reason": "   "},
], ids=["missing", "blank"])
# AC4a-N1 (negative): asking for changes needs a reason.
def test_changes_need_a_reason(body: dict) -> None:
    client, events, event_request_id, spy = safety_fixture()

    response = decide(client, event_request_id, body)

    assert response.status_code == 422
    assert_unchanged(events, event_request_id)
    assert spy.safety_changes == []


@pytest.mark.parametrize(("length", "expected"), [(1, 200), (2000, 200), (2001, 422)],
                         ids=["AC4a-B1", "AC4a-B2", "AC4a-B3"])
# AC4a-B1…B3 (boundary): the reason may be 1 to 2000 characters.
def test_reason_length_boundary(length: int, expected: int) -> None:
    client, events, event_request_id, _ = safety_fixture()

    response = decide(
        client, event_request_id, {"decision": "changes_requested", "reason": "r" * length}
    )

    assert response.status_code == expected
    if expected == 422:
        assert_unchanged(events, event_request_id)


# AC4a-N2 (negative): a target must be a venue booking or an equipment reservation.
def test_unknown_target_kind_is_refused() -> None:
    client, events, event_request_id, _ = safety_fixture()

    response = decide(
        client,
        event_request_id,
        {
            "decision": "changes_requested",
            "reason": REASON,
            "targets": [{"arrangement": "room", "id": str(uuid4())}],
        },
    )

    assert response.status_code == 422
    assert_unchanged(events, event_request_id)


# AC4a-H2 (happy): the assigned coordinator can read the officer's reason.
def test_assigned_coordinator_reads_safety_reviews() -> None:
    client, _, event_request_id, _ = safety_fixture()
    decide(client, event_request_id, {"decision": "changes_requested", "reason": REASON, "targets": TARGETS})

    with client:
        response = client.get(
            f"/event-requests/{event_request_id}/safety-reviews", headers=as_(COORDINATOR)
        )

    assert response.status_code == 200
    [review] = response.json()
    assert (review["decision"], review["reason"], review["targets"]) == (
        "changes_requested",
        REASON,
        TARGETS,
    )


@pytest.mark.parametrize(("caller", "expected"), [("coord-2", 404), ("organiser-1", 403)])
# AC4a-N3 (negative): an unassigned coordinator cannot tell the event exists;
# other roles are refused.
def test_others_cannot_read_safety_reviews(caller: str, expected: int) -> None:
    client, _, event_request_id, _ = safety_fixture()
    decide(client, event_request_id, {"decision": "changes_requested", "reason": REASON})

    with client:
        response = client.get(
            f"/event-requests/{event_request_id}/safety-reviews", headers=as_(caller)
        )

    assert response.status_code == expected
    assert response.json()["detail"] != "Not Found"  # refused by the rule, not a missing route


@pytest.mark.parametrize(("caller", "expected"), [
    (COORDINATOR, 403),
    ("organiser-1", 403),
    ("", 401),
], ids=["AC1-N1", "AC1-N2", "AC1-N3"])
# AC1-N1…N3 (negative): only a Safety Officer can record a decision.
def test_only_safety_officers_decide(caller: str, expected: int) -> None:
    client, events, event_request_id, _ = safety_fixture()

    response = decide(client, event_request_id, {"decision": "approved"}, caller=caller)

    assert response.status_code == expected
    assert_unchanged(events, event_request_id)


# AC1-N4 (negative): the database re-checks the role, so a token that outlived
# the role is refused.
def test_database_refuses_a_removed_officer() -> None:
    client, events, event_request_id, _ = safety_fixture()
    events.safety_officer_ids.clear()

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 403
    assert_unchanged(events, event_request_id)


@pytest.mark.parametrize("status", [
    "Submitted", "Under Review", "Approved", "Planning", "Confirmed", "Completed", "Cancelled",
])
# AC6-P1 (partition): a decision is only possible in Safety Review.
def test_decision_outside_safety_review_is_refused(status: str) -> None:
    client, events, event_request_id, _ = safety_fixture(status)

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 409
    assert_unchanged(events, event_request_id, status)


# AC6-N1 (negative): a repeated approval cannot record a second decision.
def test_repeated_decision_is_refused() -> None:
    client, events, event_request_id, _ = safety_fixture()
    decide(client, event_request_id, {"decision": "approved"})

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 409
    assert len(events.safety_review_rows) == 1


# AC6-N2 (negative): Reject is parked until the customer answers.
def test_reject_is_not_offered() -> None:
    client, events, event_request_id, _ = safety_fixture()

    response = decide(client, event_request_id, {"decision": "rejected", "reason": REASON})

    assert response.status_code == 422
    assert_unchanged(events, event_request_id)


# AC6-N3 (negative): a missing event is reported, not guessed.
def test_missing_event_is_reported() -> None:
    client, _, _, _ = safety_fixture()

    response = decide(client, str(uuid4()), {"decision": "approved"})

    assert response.status_code == 404
    assert response.json()["detail"] != "Not Found"  # the service's 404, not a missing route


def flag(events: FakeEventRequestRepository, event_request_id: str, cleared: bool = False) -> dict:
    """An arrangement review raised on the event by SCRUM-64 (e.g. an event change)."""
    review = {
        "id": str(uuid4()),
        "event_request_id": event_request_id,
        "arrangement": "venue_booking",
        "arrangement_id": TARGETS[0]["id"],
        "trigger_type": "event_change",
        "trigger_id": str(uuid4()),
        "reason": "Attendance changed from 120 to 300.",
        "cleared_at": "2026-10-18T09:00:00+00:00" if cleared else None,
    }
    events.arrangement_review_rows.append(review)
    return review


# AC4c-H1 (happy, SCRUM-60 2b): asking for changes marks each chosen arrangement
# for review, linked to the saved decision and carrying its reason.
def test_changes_flag_each_target_for_review() -> None:
    client, events, event_request_id, _ = safety_fixture()

    response = decide(
        client,
        event_request_id,
        {"decision": "changes_requested", "reason": REASON, "targets": TARGETS},
    )

    assert response.status_code == 200
    [review] = events.safety_review_rows
    flags = events.arrangement_review_rows
    assert sorted((f["arrangement"], f["arrangement_id"]) for f in flags) == sorted(
        (t["arrangement"], t["id"]) for t in TARGETS
    )
    assert {(f["trigger_type"], f["trigger_id"], f["reason"]) for f in flags} == {
        ("safety_recheck", review["id"], REASON)
    }


# AC4c-N1 (negative): a target from another event is refused, and nothing is
# written: no decision, no flags, status unchanged.
def test_target_from_another_event_is_refused() -> None:
    client, events, event_request_id, spy = safety_fixture()
    foreign = {"arrangement": "venue_booking", "id": str(uuid4())}
    events.arrangements.add((str(uuid4()), foreign["arrangement"], foreign["id"]))

    response = decide(
        client,
        event_request_id,
        {"decision": "changes_requested", "reason": REASON, "targets": [TARGETS[0], foreign]},
    )

    assert response.status_code == 422
    assert_unchanged(events, event_request_id)
    assert events.arrangement_review_rows == []
    assert spy.safety_changes == []


# AC6-N4 (negative): approval is refused while any arrangement is still marked
# for review, and the response lists what is outstanding.
def test_approval_refused_while_reviews_outstanding() -> None:
    client, events, event_request_id, _ = safety_fixture()
    review = flag(events, event_request_id)

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 409
    [item] = response.json()["outstanding"]
    assert (item["kind"], item["review_id"], item["arrangement_id"]) == (
        "arrangement_needs_review",
        review["id"],
        review["arrangement_id"],
    )
    assert item["message"]
    assert_unchanged(events, event_request_id)


# AC6-P2 (partition): cleared reviews no longer block approval.
def test_cleared_reviews_do_not_block_approval() -> None:
    client, events, event_request_id, _ = safety_fixture()
    flag(events, event_request_id, cleared=True)

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 200
    assert events.rows[event_request_id]["status"] == "Confirmed"


def queue(client: TestClient, caller: str = OFFICER):
    with client:
        return client.get("/event-requests/safety-queue", headers=as_(caller))


# AC2-H1 (happy, increment 3): the Safety Officer sees the events waiting for a
# check, longest-waiting first, with the details the check needs.
def test_safety_queue_lists_waiting_events_oldest_first() -> None:
    client, events, first_id, _ = safety_fixture()
    second_id = submit_event_request(events)
    planning_id = submit_event_request(events)
    events.rows[second_id].update(status="Safety Review", updated_at="2026-10-17T09:00:00+00:00")
    events.rows[first_id].update(
        updated_at="2026-10-16T09:00:00+00:00",
        expected_attendance=300,
        accessibility_needs="Step-free access to Hall B",
    )
    events.rows[planning_id]["status"] = "Planning"

    response = queue(client)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [first_id, second_id]
    assert (body[0]["expected_attendance"], body[0]["accessibility_needs"]) == (
        300,
        "Step-free access to Hall B",
    )


# AC2-P1 (partition): nothing waiting is an empty queue, not an error.
def test_empty_safety_queue() -> None:
    client, _, _, _ = safety_fixture("Planning")

    response = queue(client)

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("caller", [COORDINATOR, "organiser-1"])
# AC2-N1 (negative): only Safety Officers see the safety queue.
def test_only_safety_officers_see_the_queue(caller: str) -> None:
    client, _, _, _ = safety_fixture()

    response = queue(client, caller)

    assert response.status_code == 403


# AC6-N7 (negative, SCRUM-60 0047): approval also waits for ordinary readiness
# (SCRUM-58's event_readiness_issues); readiness items come first, then review
# flags, the same order as the handover refusal.
def test_approval_refused_until_event_is_ready() -> None:
    client, events, event_request_id, _ = safety_fixture()
    events.readiness_issues[event_request_id] = [
        {"kind": "equipment_not_reserved", "requirement_id": str(uuid4()),
         "equipment_type": "Wireless microphone", "required": 4, "reserved": 2},
    ]
    review = flag(events, event_request_id)

    response = decide(client, event_request_id, {"decision": "approved"})

    assert response.status_code == 409
    items = response.json()["outstanding"]
    assert [item["kind"] for item in items] == ["equipment_not_reserved", "arrangement_needs_review"]
    assert items[0]["message"] == "Wireless microphone: 2 of 4 reserved"
    assert items[1]["review_id"] == review["id"]
    assert_unchanged(events, event_request_id)


# AC6-P3 (partition): readiness does not block asking for changes, which is how
# the officer sends an unready event back to planning.
def test_changes_allowed_while_not_ready() -> None:
    client, events, event_request_id, _ = safety_fixture()
    events.readiness_issues[event_request_id] = [{"kind": "no_venue_booking"}]

    response = decide(client, event_request_id, {"decision": "changes_requested", "reason": REASON})

    assert response.status_code == 200
    assert events.rows[event_request_id]["status"] == "Planning"

