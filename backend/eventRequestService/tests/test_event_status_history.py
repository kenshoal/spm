from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from test_event_request_controller import FakeCoordinatorAssignmentRepository
from test_organisation_access import (
    A1,
    A2,
    B1,
    NON_DRAFT_STATUSES,
    NONE,
    OrganisationFakeRepository,
    add_request,
    client_for,
)

from app.controllers import event_request_controller
from app.main import create_app
from app.repositories import SupabaseEventRequestRepository, SupabaseRepositoryError

COORDINATOR = "cccccccc-1111-4111-8111-111111111111"


class HistoryRepository(OrganisationFakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.history_rows: list[dict] = []

    def list_status_history(self, event_request_id: str) -> list[dict]:
        return [
            dict(row)
            for row in reversed(self.history_rows)
            if row["event_request_id"] == event_request_id
        ]


def fixture(status: str = "Under Review"):
    repository = HistoryRepository()
    event_id = add_request(repository, A1, status)
    repository.history_rows = [
        {
            "id": 1,
            "event_request_id": event_id,
            "previous_status": None,
            "new_status": "Submitted",
            "actor_id": A1,
            "actor_role": "event_organiser",
            "source": "event_request.created",
            "entry_kind": "created",
            "occurred_at": "2026-10-10T01:00:00Z",
        },
        {
            "id": 2,
            "event_request_id": event_id,
            "previous_status": "Submitted",
            "new_status": status,
            "actor_id": COORDINATOR,
            "actor_role": "event_coordinator",
            "source": "coordinator.review",
            "entry_kind": "transition",
            "occurred_at": "2026-10-10T02:00:00Z",
        },
    ]
    if status == "Draft":
        repository.history_rows = [
            {**repository.history_rows[0], "new_status": "Draft"}
        ]
    elif status == "Submitted":
        repository.history_rows = repository.history_rows[:1]
    assignments = FakeCoordinatorAssignmentRepository(repository)
    assignments.create(
        {
            "event_request_id": event_id,
            "coordinator_id": COORDINATOR,
            "assigned_by": "manager",
            "assigned_at": "2026-10-10T00:00:00Z",
        }
    )
    return repository, assignments, event_id


# AC4-H1 (happy): related readers get identical chronological evidence without any write
def test_related_readers_receive_ordered_history():
    caller, roles = A1, ("event_organiser",)
    repository, assignments, event_id = fixture()
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, caller, roles, assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 200
    assert response.json() == repository.history_rows
    assert response.json()[-1]["new_status"] == repository.rows[event_id]["status"]
    assert (repository.rows, repository.history_rows) == before


@pytest.mark.parametrize(
    ("caller", "roles", "status", "code"),
    [
        (B1, ("event_organiser",), 404, "HISTORY_NOT_FOUND"),
        ("former-coordinator", ("event_coordinator",), 404, "HISTORY_NOT_FOUND"),
        ("staff", ("venue_staff",), 403, "HISTORY_FORBIDDEN"),
    ],
    ids=["AC5-P1", "AC5-P2", "AC5-P3"],
)
# AC5-P1, AC5-P2, AC5-P3 (partition): unrelated roles and relationships receive no history disclosure
def test_unrelated_readers_cannot_disclose_history(caller, roles, status, code):
    repository, assignments, event_id = fixture()
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, caller, roles, assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "actor_id" not in response.text
    assert (repository.rows, repository.history_rows) == before


# AC5-N1 (negative): same-organisation access cannot reveal another organiser's Draft history
def test_shared_colleague_cannot_read_draft_history():
    repository, assignments, event_id = fixture("Draft")
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, A2, coordinators=assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "HISTORY_NOT_FOUND"
    assert (repository.rows, repository.history_rows) == before


# AC5-N4 (negative): missing authentication cannot access retained audit actors
def test_history_requires_authentication():
    repository, assignments, event_id = fixture()
    before = deepcopy((repository.rows, repository.history_rows))
    with TestClient(create_app(repository, assignments)) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert (repository.rows, repository.history_rows) == before


# AC4-N1 (negative): a failed history lookup is an error rather than successful empty history
def test_history_database_failure_is_visible(monkeypatch):
    repository, assignments, event_id = fixture()

    def fail(_):
        raise SupabaseRepositoryError("History unavailable")

    before = deepcopy((repository.rows, repository.history_rows))
    monkeypatch.setattr(repository, "list_status_history", fail)
    with client_for(repository, A1, coordinators=assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 502
    assert response.json()["detail"] == "History unavailable"
    assert (repository.rows, repository.history_rows) == before


# AC4-X2 (cross-cutting): equal timestamps still have a deterministic event sequence
def test_equal_timestamp_history_is_ordered_by_id():
    repository, assignments, event_id = fixture()
    repository.history_rows[1]["occurred_at"] = repository.history_rows[0][
        "occurred_at"
    ]
    with client_for(repository, A1, coordinators=assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [1, 2]


# AC5-N5 (negative): history has no mutation endpoint even for the event's owner
def test_history_has_no_write_api():
    repository, assignments, event_id = fixture()
    before = deepcopy(repository.history_rows)
    with client_for(repository, A1, coordinators=assignments) as client:
        response = client.post(
            f"/event-requests/{event_id}/status-history",
            json={"new_status": "Completed"},
        )
    assert response.status_code == 405
    assert response.json()["detail"] == "Method Not Allowed"
    assert repository.history_rows == before


# AC4-H2 (happy): the real repository contract targets only the requested event and orders records
def test_supabase_history_read_is_scoped_and_ordered():
    repository, _, event_id = fixture()
    captured = []

    def handler(request):
        captured.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=repository.history_rows)

    real = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    assert real.list_status_history(event_id) == repository.history_rows
    assert captured == [
        (
            "GET",
            "/rest/v1/event_request_status_history",
            {
                "event_request_id": f"eq.{event_id}",
                "order": "occurred_at.asc,id.asc",
                "select": "*",
            },
        )
    ]


@pytest.mark.parametrize(
    "status",
    NON_DRAFT_STATUSES,
    ids=[f"AC5-P{index}" for index in range(4, 13)],
)
# AC5-P4, AC5-P5, AC5-P6, AC5-P7, AC5-P8, AC5-P9, AC5-P10, AC5-P11, AC5-P12 (partition): no non-Draft lifecycle stage silently loses permitted colleague access
def test_colleague_history_visibility_at_every_non_draft_stage(status):
    repository, assignments, event_id = fixture(status)
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, A2, coordinators=assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 200
    assert response.json() == repository.history_rows
    assert response.json()[-1]["new_status"] == status
    assert (repository.rows, repository.history_rows) == before


@pytest.mark.parametrize(
    "owned_organisation", [True, False], ids=["AC5-P13", "AC5-P17"]
)
# AC5-P13, AC5-P17 (partition): an organiser without membership cannot match either a known or absent organisation
def test_no_organisation_reader_cannot_match_an_unrelated_event(owned_organisation):
    repository, assignments, event_id = fixture()
    if not owned_organisation:
        repository.rows[event_id]["organisation_id"] = None
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, NONE, coordinators=assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "HISTORY_NOT_FOUND"
    assert "actor_id" not in response.text
    assert (repository.rows, repository.history_rows) == before


# AC5-P14 (partition): an owner retains private Draft history while colleagues are excluded
def test_owner_can_read_private_draft_history():
    repository, assignments, event_id = fixture("Draft")
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, A1, coordinators=assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 200
    assert response.json() == repository.history_rows
    assert response.json()[0]["previous_status"] is None
    assert (repository.rows, repository.history_rows) == before


# AC5-X2 (cross-cutting): access uses the current assignment instead of an earlier permitted page load
def test_reassignment_revokes_former_coordinator_history_access():
    repository, assignments, event_id = fixture()
    new_coordinator = "dddddddd-1111-4111-8111-111111111111"
    with client_for(
        repository, COORDINATOR, ("event_coordinator",), assignments
    ) as former:
        assert (
            former.get(f"/event-requests/{event_id}/status-history").status_code == 200
        )
        assignments.create(
            {
                "event_request_id": event_id,
                "coordinator_id": new_coordinator,
                "assigned_by": "manager",
            }
        )
        before = deepcopy((repository.rows, repository.history_rows, assignments.rows))
        refused = former.get(f"/event-requests/{event_id}/status-history")
    with client_for(
        repository,
        new_coordinator,
        ("event_organiser", "event_coordinator"),
        assignments,
    ) as current:
        allowed = current.get(f"/event-requests/{event_id}/status-history")
    assert refused.status_code == 404
    assert refused.json()["detail"]["code"] == "HISTORY_NOT_FOUND"
    assert "actor_id" not in refused.text
    assert allowed.status_code == 200
    assert allowed.json() == repository.history_rows
    assert (repository.rows, repository.history_rows, assignments.rows) == before


# AC5-N7 (negative): an expired token stops at the authentication boundary before any history lookup
def test_expired_authentication_does_not_query_history(monkeypatch):
    repository, assignments, event_id = fixture()
    before = deepcopy((repository.rows, repository.history_rows))
    calls = []
    monkeypatch.setattr(
        event_request_controller,
        "get_settings",
        lambda: SimpleNamespace(auth_service_url="http://auth.test"),
    )
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(401))
    monkeypatch.setattr(
        repository, "list_status_history", lambda event_id: calls.append(event_id)
    )
    with TestClient(create_app(repository, assignments)) as client:
        response = client.get(
            f"/event-requests/{event_id}/status-history",
            headers={"Authorization": "Bearer expired"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid session"
    assert calls == []
    assert (repository.rows, repository.history_rows) == before


# AC4-X3 (cross-cutting): timestamps compare actual instants rather than lexicographic local-clock strings
def test_offset_timestamps_and_equal_instants_preserve_chronology():
    repository, assignments, event_id = fixture("Approved")
    repository.history_rows[0]["occurred_at"] = "2026-10-10T09:00:00+08:00"
    repository.history_rows[1]["occurred_at"] = "2026-10-10T01:00:00Z"
    repository.history_rows[1]["new_status"] = "Under Review"
    repository.history_rows.append(
        {
            **repository.history_rows[1],
            "id": 3,
            "previous_status": "Under Review",
            "new_status": "Approved",
            "occurred_at": "2026-10-09T23:30:00-02:00",
        }
    )
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, A1, coordinators=assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [1, 2, 3]
    assert response.json()[-1]["new_status"] == repository.rows[event_id]["status"]
    assert [row["source"] for row in response.json()] == [
        row["source"] for row in repository.history_rows
    ]
    assert (repository.rows, repository.history_rows) == before


@pytest.mark.parametrize(
    "roles", [("event_coordinator",), ("event_organiser", "event_coordinator")],
    ids=["AC5-P15", "AC5-P16"],
)
# AC5-P15, AC5-P16 (partition): assigned-coordinator access survives single-role and dual-role evaluation
def test_assigned_coordinator_history_with_each_role_partition(roles):
    repository, assignments, event_id = fixture()
    before = deepcopy((repository.rows, repository.history_rows))
    with client_for(repository, COORDINATOR, roles, assignments) as client:
        response = client.get(f"/event-requests/{event_id}/status-history")
    assert response.status_code == 200
    assert response.json() == repository.history_rows
    assert (repository.rows, repository.history_rows) == before
