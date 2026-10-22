from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)
from test_event_transition_controller import assign_coordinator, headers, make_client

from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
)


def eligible_fixture(status: str = "Approved") -> tuple[TestClient, FakeEventRequestRepository, str]:
    events = FakeEventRequestRepository()
    assignments = FakeCoordinatorAssignmentRepository(events)
    event_request_id = submit_event_request(events)
    events.rows[event_request_id]["status"] = status
    assign_coordinator(assignments, event_request_id, "coord-1")
    client = make_client(events, assignments)

    def caller(authorization: str = Header()) -> AuthenticatedCaller:
        caller_id = authorization.removeprefix("Bearer ")
        role = "event_coordinator" if caller_id.startswith("coord-") else "event_organiser"
        return AuthenticatedCaller(caller_id, (role,))

    client.app.dependency_overrides[get_authenticated_caller] = caller
    return client, events, event_request_id


def change_payload(**overrides: object) -> dict[str, object]:
    return {
        "explanation": "Attendance increased after stakeholder confirmation.",
        "expected_attendance": 80,
        **overrides,
    }


# AC1-H1 (happy): retains one pending amendment without changing the approved event
def test_owner_creates_pending_change_without_mutating_event() -> None:
    client, events, event_request_id = eligible_fixture()
    before = deepcopy(events.rows[event_request_id])

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(),
        )

    assert response.status_code == 201
    assert response.json()["status"] == "Pending"
    assert response.json()["proposed_changes"] == {"expected_attendance": 80}
    assert events.rows[event_request_id] == before
    assert len(events.change_request_rows) == 1


@pytest.mark.parametrize("event_status", ["Approved", "Planning"], ids=["AC1-P1", "AC1-P2"])
# AC1-P1, AC1-P2 (partition): both approved planning states accept an amendment
def test_eligible_event_statuses_accept_change_request(event_status: str) -> None:
    client, events, event_request_id = eligible_fixture(event_status)

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(),
        )

    assert response.status_code == 201
    assert events.rows[event_request_id]["status"] == event_status


# AC1-N1 (negative): refuses an explanation with no proposed event-field change
def test_change_request_requires_at_least_one_changed_field() -> None:
    client, events, event_request_id = eligible_fixture()

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json={"explanation": "Please update the plan."},
        )

    assert response.status_code == 422
    assert events.change_request_rows == []


# AC1-N2 (negative): a submitted value must differ from the stored event value
def test_change_request_rejects_unchanged_value() -> None:
    client, events, event_request_id = eligible_fixture()
    events.rows[event_request_id]["expected_attendance"] = 80

    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(expected_attendance=80),
        )

    assert response.status_code == 409
    assert events.rows[event_request_id]["expected_attendance"] == 80
    assert events.change_request_rows == []


@pytest.mark.parametrize(("length", "expected"), [(1, 201), (2000, 201), (2001, 422)], ids=["AC1-B1", "AC1-B2", "AC1-B3"])
# AC1-B1, AC1-B2, AC1-B3 (boundary): explanation limits accept 1/2000 and reject 2001 characters
def test_change_explanation_boundaries(length: int, expected: int) -> None:
    client, events, event_request_id = eligible_fixture()
    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(explanation="x" * length),
        )
    assert response.status_code == expected
    assert len(events.change_request_rows) == (1 if expected == 201 else 0)


@pytest.mark.parametrize(
    "event_status",
    ["Draft", "Submitted", "Under Review", "Changes Requested", "Confirmed", "Completed", "Cancelled", "Rejected"],
    ids=[f"AC5-P{index}" for index in range(1, 9)],
)
# AC5-P1–P8 (partition): statuses outside Approved and Planning cannot gain amendment rows
def test_disallowed_event_statuses_refuse_change(event_status: str) -> None:
    client, events, event_request_id = eligible_fixture(event_status)
    with client:
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(),
        )
    assert response.status_code == 409
    assert events.rows[event_request_id]["status"] == event_status
    assert events.change_request_rows == []


# AC2-N1 (negative): another organiser receives no evidence that the event exists
def test_other_organiser_cannot_create_or_view_change_request() -> None:
    client, events, event_request_id = eligible_fixture()

    with client:
        create = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-2"),
            json=change_payload(),
        )
        listing = client.get(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-2"),
        )
        coordinator_listing = client.get(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("coord-2"),
        )

    assert create.status_code == 404
    assert listing.status_code == 404
    assert coordinator_listing.status_code == 404
    assert events.change_request_rows == []


# AC2-X1 (cross-cutting): owner and current coordinator see the same retained history
def test_owner_and_assigned_coordinator_can_view_change_request() -> None:
    client, _events, event_request_id = eligible_fixture()

    with client:
        created = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(),
        )
        owner_listing = client.get(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
        )
        coordinator_listing = client.get(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("coord-1"),
        )

    assert created.status_code == 201
    assert owner_listing.status_code == 200
    assert coordinator_listing.status_code == 200
    assert owner_listing.json() == [created.json()]
    assert coordinator_listing.json() == [created.json()]


# AC4-N1 (negative): a rejection without a reason is stopped before any write
def test_rejection_requires_reason() -> None:
    client, events, event_request_id = eligible_fixture()
    with client:
        created = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(),
        ).json()
        before = deepcopy(events.rows[event_request_id])
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests/{created['id']}/decision",
            headers=headers("coord-1"),
            json={"decision": "Rejected", "reason": "   "},
        )
    assert response.status_code == 422
    assert events.rows[event_request_id] == before
    assert events.change_request_rows[0]["status"] == "Pending"


# AC5-N1 (negative): a second pending amendment is refused without adding another row
def test_only_one_pending_change_request_is_allowed() -> None:
    client, events, event_request_id = eligible_fixture()
    with client:
        first = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(),
        )
        second = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(expected_attendance=90),
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert len(events.change_request_rows) == 1


# AC5-N3 (negative): reassignment removes the former coordinator's decision authority
def test_former_coordinator_cannot_decide_after_reassignment() -> None:
    client, events, event_request_id = eligible_fixture()
    assignments = client.app.state.coordinator_assignment_service.repository
    with client:
        created = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"),
            json=change_payload(),
        ).json()
        assign_coordinator(assignments, event_request_id, "coord-2")
        before = deepcopy(events.rows[event_request_id])
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests/{created['id']}/decision",
            headers=headers("coord-1"),
            json={"decision": "Approved"},
        )
    assert response.status_code == 403
    assert events.rows[event_request_id] == before
    assert events.change_request_rows[0]["status"] == "Pending"


@pytest.mark.parametrize("decision", ["Approved"], ids=["AC2-N2"])
# AC2-N2 (negative): an unsupported stored capacity proposal cannot call any decision primitive, notify or partially apply otherwise supported values
def test_change_decisions_are_unavailable_without_side_effects(decision: str, monkeypatch: pytest.MonkeyPatch) -> None:
    client, events, event_request_id = eligible_fixture()
    service = client.app.state.event_request_service
    decision_spy = Mock(side_effect=AssertionError("Deferred decision primitive must not run"))
    monkeypatch.setattr(service, "decide_change_request", decision_spy)
    notification_spy = Mock()
    monkeypatch.setattr("httpx.post", notification_spy)
    with client:
        created = client.post(
            f"/event-requests/{event_request_id}/change-requests",
            headers=headers("organiser-1"), json=change_payload(),
        )
        assert created.status_code == 201
        # A stored unsupported key must not be partially applied even though normal creation rejects that field.
        events.change_request_rows[0]["proposed_changes"]["registration_capacity"] = 99
        before_event = deepcopy(events.rows[event_request_id])
        before_changes = deepcopy(events.change_request_rows)
        response = client.post(
            f"/event-requests/{event_request_id}/change-requests/{created.json()['id']}/decision",
            headers=headers("coord-1"),
            json={"decision": decision, "reason": "The proposal needs staff assessment."},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CHANGE_DECISIONS_UNAVAILABLE"
    assert events.rows[event_request_id] == before_event
    assert events.change_request_rows == before_changes
    decision_spy.assert_not_called()
    notification_spy.assert_not_called()
