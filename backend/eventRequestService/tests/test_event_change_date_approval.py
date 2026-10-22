"""SCRUM-35 date decision wire; prepared RPC output is not native transaction proof."""

import json
from copy import deepcopy

import pytest
from test_event_change_date_plan import NEW, OLD
from test_event_change_request import eligible_fixture
from test_event_transition_controller import headers

from app.repositories import EventRequestRpcError


# AC3-H5 (happy): supported automatic date approval reaches the date-only transaction and preserves its complete saved plan/audit instead of the legacy refusal.
def test_current_coordinator_approves_dates_with_complete_saved_plan(monkeypatch):
    client, repository, event_id = eligible_fixture("Planning")
    repository.rows[event_id]["proposed_date_times"] = deepcopy(OLD)
    created = client.post(
        f"/event-requests/{event_id}/change-requests", headers=headers("organiser-1"),
        json={"explanation": "Move the agreed activity by two calendar days.", "proposed_date_times": NEW},
    )
    assert created.status_code == 201, created.text
    pending = created.json()
    plan = [
        {"booking_id": "35000000-0000-4000-8000-000000000801", "start_date": "2026-11-22", "end_date": "2026-11-23", "start_minute": 600, "end_minute": 720},
        {"booking_id": "35000000-0000-4000-8000-000000000802", "start_date": "2026-11-23", "end_date": "2026-11-24", "start_minute": 900, "end_minute": 1080},
    ]
    saved = {**pending, "status": "Approved", "coordinator_id": "coord-1", "decision_reason": "Checked the complete venue plan.", "decided_at": "2026-10-22T12:00:00Z", "applied_booking_plan": plan}
    calls = []

    def date_result(event, change, actor, reason, booking_plan):
        calls.append((event, change, actor, reason, deepcopy(booking_plan)))
        return deepcopy(saved)

    def legacy_forbidden(*args, **kwargs):
        raise AssertionError("Date approval must not use the legacy non-date/rejection transaction")

    monkeypatch.setattr(repository, "approve_date_change_request", date_result, raising=False)
    monkeypatch.setattr(repository, "decide_change_request", legacy_forbidden)
    before = deepcopy(repository.rows), deepcopy(repository.change_request_rows)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/change-requests/{pending['id']}/decision",
            headers=headers("coord-1"), json={"decision": "Approved", "reason": saved["decision_reason"]},
        )
    assert response.status_code == 200, response.text
    assert response.json() == saved
    assert calls == [(event_id, pending["id"], "coord-1", saved["decision_reason"], None)]
    assert (repository.rows, repository.change_request_rows) == before


def date_decision_fixture(monkeypatch, changes=None):
    client, repository, event = eligible_fixture("Planning")
    repository.rows[event]["proposed_date_times"] = deepcopy(OLD)
    payload = changes or {"proposed_date_times": ["2026-11-22T11:00:00+08:00", "2026-11-24T16:00:00+08:00"], "expected_attendance": 40, "registration_needs": "Accessible online form"}
    created = client.post(f"/event-requests/{event}/change-requests", headers=headers("organiser-1"), json={"explanation": "Use the coordinator's explicit complete venue plan.", **payload})
    assert created.status_code == 201, created.text
    pending = created.json()
    plan = [{"booking_id": "35000000-0000-4000-8000-000000000803", "start_date": "2026-11-22", "end_date": "2026-11-22", "start_minute": 660, "end_minute": 750}]
    saved = {**pending, "status": "Approved", "coordinator_id": "coord-1", "decision_reason": None, "decided_at": "2026-10-22T12:00:00Z", "applied_booking_plan": plan}
    calls = []

    def result(*args):
        calls.append(deepcopy(args))
        return deepcopy(saved)

    monkeypatch.setattr(repository, "approve_date_change_request", result, raising=False)
    return client, repository, event, pending, plan, saved, calls


# AC3-H6 (happy): changed event wall times plus supported mixed fields forward the exact explicit booking ranges and preserve the native saved plan/audit.
def test_explicit_complete_plan_is_forwarded_for_mixed_date_approval(monkeypatch):
    client, repository, event, pending, plan, saved, calls = date_decision_fixture(monkeypatch)
    before = deepcopy(repository.rows), deepcopy(repository.change_request_rows), deepcopy(plan)
    with client:
        response = client.post(f"/event-requests/{event}/change-requests/{pending['id']}/decision", headers=headers("coord-1"), json={"decision": "Approved", "booking_plan": plan})
    assert response.status_code == 200, response.text
    assert response.json() == saved
    assert calls == [(event, pending["id"], "coord-1", None, plan)]
    assert (repository.rows, repository.change_request_rows, plan) == before


# AC2-N11 (negative): a booking plan on rejection or a non-date proposal must be refused rather than silently ignored or sent to a mutation.
@pytest.mark.parametrize(("decision", "changes"), [("Rejected", {"proposed_date_times": NEW}), ("Approved", {"expected_attendance": 40})], ids=["AC2-N11-rejected", "AC2-N11-nondate"])
def test_irrelevant_booking_plan_is_not_silently_ignored(monkeypatch, decision, changes):
    client, repository, event, pending, plan, _, calls = date_decision_fixture(monkeypatch, changes)

    def forbidden(*args, **kwargs):
        raise AssertionError("An irrelevant booking plan must not reach any mutation")

    monkeypatch.setattr(repository, "decide_change_request", forbidden)
    before = deepcopy(repository.rows), deepcopy(repository.change_request_rows)
    with client:
        response = client.post(f"/event-requests/{event}/change-requests/{pending['id']}/decision", headers=headers("coord-1"), json={"decision": decision, "reason": "Reasoned refusal", "booking_plan": plan})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]
    assert calls == []
    assert (repository.rows, repository.change_request_rows) == before


# AC3-N25 (negative): an explicit plan cannot smuggle a replacement venue identity into an otherwise valid range.
def test_explicit_plan_rejects_unaccepted_identity_fields(monkeypatch):
    client, repository, event, pending, plan, _, calls = date_decision_fixture(monkeypatch)
    plan[0]["venue_id"] = "35000000-0000-4000-8000-000000000999"
    before = deepcopy(repository.rows), deepcopy(repository.change_request_rows)
    with client:
        response = client.post(f"/event-requests/{event}/change-requests/{pending['id']}/decision", headers=headers("coord-1"), json={"decision": "Approved", "booking_plan": plan})
    assert response.status_code == 422, response.text
    assert any(error["type"] == "extra_forbidden" for error in response.json()["detail"])
    assert calls == []
    assert (repository.rows, repository.change_request_rows) == before


# AC4-N7 (negative): native conflict evidence becomes a safe structured refusal, never a generic success or raw SQL disclosure.
def test_native_date_conflict_returns_safe_per_booking_evidence(monkeypatch):
    client, repository, event, pending, plan, _, calls = date_decision_fixture(monkeypatch)
    evidence = [{"booking_id": plan[0]["booking_id"], "refusal_codes": ["active_block"], "conflicting_booking_ids": [], "conflicting_block_ids": ["35000000-0000-4000-8000-000000000998"]}]

    def conflict(*args):
        calls.append(deepcopy(args))
        raise EventRequestRpcError("private_sql_relation_details", "P0005", json.dumps(evidence))

    monkeypatch.setattr(repository, "approve_date_change_request", conflict)
    before = deepcopy(repository.rows), deepcopy(repository.change_request_rows)
    with client:
        response = client.post(f"/event-requests/{event}/change-requests/{pending['id']}/decision", headers=headers("coord-1"), json={"decision": "Approved", "booking_plan": plan})
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert set(detail) == {"code", "message", "bookings"}
    assert detail["code"] == "BOOKING_CONFLICT" and isinstance(detail["message"], str) and detail["message"].strip()
    assert detail["bookings"] == evidence
    assert "private_sql_relation_details" not in response.text
    assert calls == [(event, pending["id"], "coord-1", None, plan)]
    assert (repository.rows, repository.change_request_rows) == before
