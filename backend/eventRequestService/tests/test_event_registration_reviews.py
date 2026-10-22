"""Approved SCRUM-35 registration review contract; native state/gates are verified separately."""

from copy import deepcopy
from datetime import datetime
from typing import Any

import pytest
from test_arrangement_reviews import (
    COORDINATOR,
    EVENT,
    OTHER_EVENT,
    REPLACEMENT,
    fixture,
)
from test_event_change_approval import approve, create_nondate_pending
from test_event_change_rejection import comparable_change
from test_event_change_request import eligible_fixture
from test_organisation_access import A1, client_for

from app.repositories import EventRequestRpcError, SupabaseRepositoryError

ACK_TIME = "2026-10-22T11:00:00Z"


def review(number: int, **overrides: Any) -> dict:
    return {
        "id": f"35000000-0000-4000-8000-{number:012d}",
        "event_request_id": EVENT,
        "event_updated_at": f"2026-10-22T00:0{number}:00Z",
        "changed_fields": ["registration_needs"],
        "reason": f"registration_needs: 'Paper form' -> 'Online form {number}'",
        "raised_at": "2026-10-22T01:00:00Z",
        "cleared_at": None,
        "cleared_by": None,
        **overrides,
    }


def review_fixture():
    repository, assignments = fixture()
    repository.registration_rows = [
        review(1), review(3, cleared_at=ACK_TIME, cleared_by=COORDINATOR),
        review(4, event_request_id=OTHER_EVENT), review(2),
    ]
    repository.registration_reads = []
    repository.registration_ack_calls = []
    repository.registration_ack_result = None
    repository.registration_ack_error = None
    repository.registration_read_error = None

    # The existing repository fake is extended only with event-equality storage and prepared RPC outcomes.
    def read(event_id):
        repository.registration_reads.append(event_id)
        if repository.registration_read_error is not None:
            raise repository.registration_read_error
        return deepcopy([row for row in repository.registration_rows if row["event_request_id"] == event_id])

    def acknowledge(event_id, review_id, actor_id):
        repository.registration_ack_calls.append((event_id, review_id, actor_id))
        if repository.registration_ack_error is not None:
            raise repository.registration_ack_error
        assert repository.registration_ack_result is not None, "SETUP: prepared RPC result required"
        return deepcopy(repository.registration_ack_result)

    repository.list_registration_reviews = read
    repository.acknowledge_registration_review = acknowledge
    return repository, assignments


def protected(repository):
    return deepcopy({
        key: value for key, value in vars(repository).items()
        if not key.startswith("registration_ack_") and key not in {
            "registration_reads", "registration_read_error", "list_registration_reviews", "acknowledge_registration_review",
        }
    })


def normalized(row):
    return {
        **row,
        **{field: datetime.fromisoformat(row[field]) if row[field] else None
           for field in ("event_updated_at", "raised_at", "cleared_at")},
    }


def failure(response, status, code):
    assert response.status_code == status
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("code") == code
    assert "Paper form" not in response.text and "private_storage_detail" not in response.text


# AC3-H4 (happy): registration requirements are supported non-date text, while attendee/window/capacity and unrelated plan values remain untouched.
def test_registration_text_only_approval_saves_exact_decision_and_owner_outcome():
    client, repository, event_id = eligible_fixture("Planning")
    with client:
        pending = create_nondate_pending(client, event_id, registration_needs="Accessible online registration form")
        before = deepcopy(repository.rows)
        response = approve(client, event_id, pending["id"])
    assert response.status_code == 200
    saved = response.json()
    assert saved == {**pending, "status": "Approved", "coordinator_id": "coord-1", "decision_reason": None, "decided_at": saved["decided_at"]}
    assert saved["decided_at"] is not None and datetime.fromisoformat(saved["decided_at"]).utcoffset() is not None
    assert [comparable_change(row) for row in repository.change_request_rows] == [comparable_change(saved)]
    expected = deepcopy(before)
    expected[event_id].update({"registration_needs": "Accessible online registration form", "updated_at": repository.rows[event_id]["updated_at"]})
    assert repository.rows == expected


# AC3-X18, AC3-P4 (partition): owner and current coordinator retain the complete acknowledged/outstanding history in deterministic newest-first order.
@pytest.mark.parametrize(("actor", "roles"), [(A1, ("event_organiser",)), (COORDINATOR, ("event_coordinator",))], ids=["AC3-X18", "AC3-P4"])
def test_authorised_reader_sees_all_retained_registration_evidence(actor, roles):
    repository, assignments = review_fixture()
    before = protected(repository)
    expected = [repository.registration_rows[index] for index in (1, 3, 0)]
    with client_for(repository, actor, roles, assignments) as client:
        response = client.get(f"/event-requests/{EVENT}/registration-reviews")
    assert response.status_code == 200
    assert [normalized(row) for row in response.json()] == [normalized(row) for row in expected]
    assert repository.registration_reads == [EVENT]
    assert protected(repository) == before


# AC3-X19 (cross-cutting): only the verified current coordinator acknowledges the exact older record; organiser read access does not confer write access.
def test_exact_registration_acknowledgement_uses_verified_actor():
    repository, assignments = review_fixture()
    older = repository.registration_rows[0]
    repository.registration_ack_result = {**older, "cleared_at": ACK_TIME, "cleared_by": COORDINATOR}
    before = protected(repository)
    with client_for(repository, A1, ("event_organiser",), assignments) as owner:
        denied = owner.post(f"/event-requests/{EVENT}/registration-reviews/{older['id']}/acknowledge")
    failure(denied, 403, "REGISTRATION_REVIEW_FORBIDDEN")
    assert repository.registration_ack_calls == []
    with client_for(repository, COORDINATOR, ("event_coordinator",), assignments) as client:
        response = client.post(f"/event-requests/{EVENT}/registration-reviews/{older['id']}/acknowledge", json={"actor_id": REPLACEMENT})
    assert response.status_code == 200
    assert normalized(response.json()) == normalized(repository.registration_ack_result)
    assert repository.registration_ack_calls == [(EVENT, older["id"], COORDINATOR)]
    assert protected(repository) == before


# AC3-N20, AC3-N21, AC3-N22, AC3-N23 (negative): authoritative missing/assignment/repeat/storage failures remain specific and never announce a false acknowledgement or leak private detail.
@pytest.mark.parametrize(
    ("error", "status", "code"),
    [(EventRequestRpcError("Missing", "P0002"), 404, "REGISTRATION_REVIEW_NOT_FOUND"),
     (EventRequestRpcError("Reassigned", "P0003"), 403, "REGISTRATION_REVIEW_FORBIDDEN"),
     (EventRequestRpcError("Already acknowledged", "P0004"), 409, "REGISTRATION_REVIEW_ALREADY_ACKNOWLEDGED"),
     (SupabaseRepositoryError("private_storage_detail"), 502, None)],
    ids=["AC3-N20", "AC3-N21", "AC3-N22", "AC3-N23"],
)
def test_registration_acknowledgement_refusal_preserves_evidence(error, status, code):
    repository, assignments = review_fixture()
    older = repository.registration_rows[0]
    repository.registration_ack_error = error
    before = protected(repository)
    with client_for(repository, COORDINATOR, ("event_coordinator",), assignments) as client:
        response = client.post(f"/event-requests/{EVENT}/registration-reviews/{older['id']}/acknowledge")
        if status == 502:
            repository.registration_read_error = error
            failed_read = client.get(f"/event-requests/{EVENT}/registration-reviews")
    if status == 502:
        assert (response.status_code, response.json()) == (502, {"detail": "Registration reviews unavailable"})
        assert (failed_read.status_code, failed_read.json()) == (502, {"detail": "Registration reviews unavailable"})
    else:
        failure(response, status, code)
    assert protected(repository) == before


# AC2-N9 (negative): an unrelated coordinator cannot disclose another event's registration-review history or reach its repository read.
def test_unrelated_coordinator_cannot_read_registration_evidence():
    repository, assignments = review_fixture()
    before = protected(repository)
    with client_for(repository, REPLACEMENT, ("event_coordinator",), assignments) as client:
        response = client.get(f"/event-requests/{EVENT}/registration-reviews")
    failure(response, 404, "REGISTRATION_REVIEW_NOT_FOUND")
    assert repository.registration_reads == []
    assert protected(repository) == before
