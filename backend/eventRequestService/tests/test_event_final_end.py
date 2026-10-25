"""Actual FastAPI setter contract; prepared storage outcomes leave native rules to SQL."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)
from test_event_transition_controller import assign_coordinator, headers, make_client

from app.models.event_request import EventRequestResponse
from app.repositories import EventRequestRpcError, SupabaseRepositoryError

END = "2026-11-25T18:30:00+08:00"
END_UTC = datetime(2026, 11, 25, 10, 30, tzinfo=UTC)


def fixture(status="Approved", outcome=None):
    events = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository(events)
    event_id = submit_event_request(events)
    events.rows[event_id].update(status=status, final_event_end_at=None)
    assign_coordinator(coordinators, event_id, "coord-1")
    saved = {
        **deepcopy(events.rows[event_id]),
        "final_event_end_at": END,
        "updated_at": "2026-10-23T05:00:00Z",
    }
    calls = []

    def set_final_end(event_request_id, coordinator_id, final_event_end_at):
        calls.append((event_request_id, coordinator_id, final_event_end_at))
        if isinstance(outcome, Exception):
            raise outcome
        return deepcopy(saved)

    events.set_final_end = set_final_end
    return make_client(events, coordinators), events, event_id, saved, calls


def protected(events):
    return deepcopy(
        {key: value for key, value in vars(events).items() if key != "set_final_end"}
    )


@pytest.mark.parametrize("status", ["Approved", "Planning"], ids=["AC1-H3", "AC1-P1"])
# AC1-H3, AC1-P1 (partition): the assigned coordinator records an aware authoritative end in either editable state without applying another workflow.
def test_assigned_coordinator_records_final_end(status):
    client, events, event_id, saved, calls = fixture(status)
    before = protected(events)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/final-end",
            headers=headers("coord-1"),
            json={"final_event_end_at": END},
        )
    assert response.status_code == 200, response.text
    assert response.json() == EventRequestResponse.model_validate(saved).model_dump(
        mode="json"
    )
    assert datetime.fromisoformat(response.json()["final_event_end_at"]) == END_UTC
    assert response.json()["status"] == status
    assert calls == [(event_id, "coord-1", END_UTC)]
    assert protected(events) == before


# AC1-N3 (negative): an obsolete assignee cannot invoke the authoritative write boundary or alter the recorded plan.
def test_wrong_assignment_cannot_record_final_end():
    client, events, event_id, _, calls = fixture()
    assign_coordinator(
        client.app.state.coordinator_assignment_service.repository, event_id, "coord-2"
    )
    before = protected(events)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/final-end",
            headers=headers("coord-1"),
            json={"final_event_end_at": END},
        )
    assert response.status_code == 403
    assert isinstance(response.json()["detail"], str) and response.json()["detail"]
    assert calls == []
    assert protected(events) == before


@pytest.mark.parametrize(
    "body",
    [{}, {"final_event_end_at": "2026-11-25T18:30:00"}],
    ids=["missing", "naive"],
)
# AC1-N4 (negative): a missing or timezone-free end is validation failure before any protected write.
def test_final_end_requires_aware_timestamp(body):
    client, events, event_id, _, calls = fixture()
    before = protected(events)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/final-end",
            headers=headers("coord-1"),
            json=body,
        )
    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", "final_event_end_at"]
        and error["type"] in {"missing", "timezone_aware"}
        for error in response.json()["detail"]
    )
    assert calls == []
    assert protected(events) == before


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (EventRequestRpcError("private SQL detail", "P0002"), 404, None),
        (EventRequestRpcError("private SQL detail", "P0003"), 403, None),
        (
            EventRequestRpcError("private SQL detail", "P0004"),
            409,
            "final_end_unavailable",
        ),
        (SupabaseRepositoryError("private SQL detail"), 502, None),
    ],
    ids=[
        "missing-event",
        "reassigned-at-write",
        "state-changed-at-write",
        "storage-outage",
    ],
)
# AC1-N5 (negative): locked native refusals and an outage map safely rather than announcing a saved end or exposing database details.
def test_refused_native_setter_is_safe_and_preserves_state(error, status, code):
    client, events, event_id, _, calls = fixture(outcome=error)
    before = protected(events)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/final-end",
            headers=headers("coord-1"),
            json={"final_event_end_at": END},
        )
    assert response.status_code == status
    if code:
        assert response.json()["detail"]["code"] == code
    elif status == 502:
        assert response.json() == {"detail": "Final event end unavailable"}
    else:
        assert isinstance(response.json()["detail"], str) and response.json()["detail"]
    assert "private SQL detail" not in response.text
    assert calls == [(event_id, "coord-1", END_UTC)]
    assert protected(events) == before


# AC1-N7 (negative): missing bearer reaches real authentication and cannot invoke the new end setter or another service.
def test_missing_authentication_cannot_record_final_end(monkeypatch):
    from unittest.mock import Mock

    import httpx

    from app.controllers import event_request_controller as controller

    client, events, event_id, _, calls = fixture()
    before = protected(events)
    client.app.dependency_overrides.pop(controller.get_coordinator_id)
    network = Mock(side_effect=AssertionError("Missing bearer must not call Auth HTTP"))
    monkeypatch.setattr(httpx, "get", network)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/final-end", json={"final_event_end_at": END}
        )
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    network.assert_not_called()
    assert calls == []
    assert protected(events) == before


# AC1-N8 (negative): verified organiser ownership cannot confer coordinator authority over the final event end.
def test_organiser_cannot_record_final_end(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import httpx

    from app.controllers import event_request_controller as controller

    client, events, event_id, _, calls = fixture()
    owner = "40000000-0000-4000-8000-000000000099"
    events.rows[event_id]["organiser_id"] = owner
    before = protected(events)
    client.app.dependency_overrides.pop(controller.get_coordinator_id)
    monkeypatch.setattr(
        controller,
        "get_settings",
        lambda: SimpleNamespace(auth_service_url="https://auth.test"),
    )
    auth = Mock(
        return_value=httpx.Response(
            200,
            json={"id": owner, "roles": ["event_organiser"]},
            request=httpx.Request("GET", "https://auth.test/auth/me"),
        )
    )
    monkeypatch.setattr(httpx, "get", auth)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/final-end",
            headers=headers("organiser-session"),
            json={"final_event_end_at": END},
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    auth.assert_called_once_with(
        "https://auth.test/auth/me", headers=headers("organiser-session"), timeout=10
    )
    assert calls == []
    assert protected(events) == before
