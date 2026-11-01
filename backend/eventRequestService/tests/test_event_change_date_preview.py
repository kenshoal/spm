"""Read-only preview API: real FastAPI/planner, raw storage/Auth doubles only."""

from copy import deepcopy

import pytest
from test_event_change_date_plan import NEW, OLD, bookings
from test_event_change_request import eligible_fixture
from test_event_transition_controller import assign_coordinator, headers

from app.repositories import SupabaseRepositoryError


def fixture(monkeypatch, status="Approved"):
    client, repository, event = eligible_fixture(status)
    repository.rows[event]["proposed_date_times"] = deepcopy(OLD)
    repository.rows[event]["updated_at"] = "2026-10-22T01:00:00+00:00"
    created = client.post(
        f"/event-requests/{event}/change-requests", headers=headers("organiser-1"),
        json={"explanation": "Move both dates by the agreed calendar shift.", "proposed_date_times": NEW},
    )
    assert created.status_code == 201, created.text
    change = created.json()
    repository.change_request_rows[0]["base_event_updated_at"] = "2026-10-22T01:00:00Z"
    repository.preview_bookings = [
        {**row, "id": f"35000000-0000-4000-8000-{number:012d}", "venue_id": f"35000000-0000-4000-8000-{100 + number:012d}", "event_request_id": event}
        for number, row in enumerate(bookings(), 1)
    ]
    repository.preview_calls = []

    def get_change(event_id, change_id):
        repository.preview_calls.append(("change", event_id, change_id))
        return deepcopy(next((row for row in repository.change_request_rows if row["id"] == change_id and row["event_request_id"] == event_id), None))

    def get_bookings(event_id):
        repository.preview_calls.append(("bookings", event_id))
        return deepcopy([row for row in repository.preview_bookings if row["event_request_id"] == event_id])

    monkeypatch.setattr(repository, "get_change_request", get_change, raising=False)
    monkeypatch.setattr(repository, "list_event_venue_bookings", get_bookings, raising=False)
    return client, repository, event, change["id"]


def protected(repository):
    return deepcopy({key: value for key, value in vars(repository).items() if key not in {"preview_calls", "get_change_request", "list_event_venue_bookings"}})


def url(event, change):
    return f"/event-requests/{event}/change-requests/{change}/date-plan"


def expected(event, change):
    return {"event_request_id": event, "change_request_id": change, "advisory": True, "bookings": [
        {"booking_id": "35000000-0000-4000-8000-000000000001", "venue_id": "35000000-0000-4000-8000-000000000101", "status": "pending", "current_start_date": "2026-11-19", "current_end_date": "2026-11-20", "proposed_start_date": "2026-11-21", "proposed_end_date": "2026-11-22", "start_minute": 600, "end_minute": 720},
        {"booking_id": "35000000-0000-4000-8000-000000000002", "venue_id": "35000000-0000-4000-8000-000000000102", "status": "approved", "current_start_date": "2026-11-20", "current_end_date": "2026-11-23", "proposed_start_date": "2026-11-22", "proposed_end_date": "2026-11-25", "start_minute": 900, "end_minute": 1080},
    ]}


@pytest.mark.parametrize("status", ["Approved", "Planning"], ids=["AC3-H3", "AC3-P3"])
# AC3-H3, AC3-P3 (partition): either eligible event returns a complete advisory plan without changing any stored proposal, plan or arrangement evidence.
def test_current_coordinator_gets_complete_readonly_plan(monkeypatch, status):
    client, repository, event, change = fixture(monkeypatch, status)
    before = protected(repository)
    with client:
        response = client.get(url(event, change), headers=headers("coord-1"))
    assert response.status_code == 200, response.text
    assert response.json() == expected(event, change)
    assert repository.preview_calls == [("change", event, change), ("bookings", event)]
    assert protected(repository) == before


# AC2-N6 (negative): reassignment revokes access before protected booking data is queried.
def test_wrong_assignment_cannot_read_booking_plan(monkeypatch):
    client, repository, event, change = fixture(monkeypatch)
    assign_coordinator(client.app.state.coordinator_assignment_service.repository, event, "coord-2")
    before = protected(repository)
    with client:
        response = client.get(url(event, change), headers=headers("coord-1"))
    assert response.status_code == 403
    assert response.json() == {"detail": "Only the assigned coordinator can access this change"}
    assert not any(call[0] == "bookings" for call in repository.preview_calls)
    assert protected(repository) == before


@pytest.mark.parametrize(
    ("kind", "code"),
    [("stale", "change_request_stale"), ("state", "date_plan_unavailable"), ("mixed", "unsupported_date_mapping")],
    ids=["AC6-N1", "AC3-N3", "AC2-N2"],
)
# AC6-N1, AC3-N3, AC2-N2 (negative): obsolete state or unsupported scope refuses the entire advisory query without reading bookings or applying a partial plan.
def test_refused_preview_has_specific_code_and_no_effects(monkeypatch, kind, code):
    client, repository, event, change = fixture(monkeypatch)
    if kind == "stale":
        repository.rows[event]["updated_at"] = "2026-10-22T01:00:01Z"
    elif kind == "state":
        # Hotfix 9 made Confirmed changeable, so a closed event is the obsolete state.
        repository.rows[event]["status"] = "Completed"
    else:
        repository.change_request_rows[0]["proposed_changes"]["expected_attendance"] = 80
    before = protected(repository)
    with client:
        response = client.get(url(event, change), headers=headers("coord-1"))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("code") == code
    assert not any(call[0] == "bookings" for call in repository.preview_calls)
    assert protected(repository) == before


# AC3-N12 (negative): an existing proposal belonging to another event cannot be borrowed by the scoped preview route.
def test_foreign_proposal_is_not_found_without_booking_disclosure(monkeypatch):
    client, repository, event, change = fixture(monkeypatch)
    repository.change_request_rows[0]["event_request_id"] = "35000000-0000-4000-8000-000000000099"
    before = protected(repository)
    with client:
        response = client.get(url(event, change), headers=headers("coord-1"))
    assert response.status_code == 404
    assert response.json() == {"detail": "Change request not found"}
    assert not any(call[0] == "bookings" for call in repository.preview_calls)
    assert protected(repository) == before


# AC3-N13 (negative): storage failure cannot become an empty advisory plan or disclose private database details.
def test_booking_storage_failure_is_safe_and_readonly(monkeypatch):
    client, repository, event, change = fixture(monkeypatch)

    def unavailable(event_id):
        raise SupabaseRepositoryError("private_SQL_detail: unavailable booking relation")

    monkeypatch.setattr(repository, "list_event_venue_bookings", unavailable)
    before = protected(repository)
    with client:
        response = client.get(url(event, change), headers=headers("coord-1"))
    assert response.status_code == 502
    assert response.json() == {"detail": "Date change plan unavailable"}
    assert "private_SQL_detail" not in response.text
    assert protected(repository) == before
