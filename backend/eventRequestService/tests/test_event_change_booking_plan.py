"""Complete coordinator editor context; real API/planner, event-equality storage doubles."""

from copy import deepcopy

import pytest
from test_event_change_date_preview import fixture, protected
from test_event_transition_controller import headers


# AC3-X25, AC3-P5 (partition): the coordinator editor receives complete current ranges even when automatic mapping is unavailable, without changing the proposal or plan.
@pytest.mark.parametrize("manual", [False, True], ids=["AC3-X25", "AC3-P5"])
def test_complete_booking_context_supports_automatic_and_explicit_editor(monkeypatch, manual):
    client, repository, event, change = fixture(monkeypatch, "Planning")
    repository.change_request_rows[0]["proposed_changes"].update({"expected_attendance": 40, "registration_needs": "Online registration"})
    if manual:
        repository.change_request_rows[0]["proposed_changes"]["proposed_date_times"] = [
            "2026-11-22T11:00:00+08:00", "2026-11-24T16:00:00+08:00",
        ]
    before = protected(repository)
    rows = repository.preview_bookings
    current = [{
        "booking_id": row["id"], "venue_id": row["venue_id"], "status": row["status"],
        "start_date": row["start_date"], "end_date": row["end_date"],
        "start_minute": row["start_minute"], "end_minute": row["end_minute"],
    } for row in rows[:2]]
    automatic = [
        {"booking_id": rows[0]["id"], "start_date": "2026-11-21", "end_date": "2026-11-22", "start_minute": 600, "end_minute": 720},
        {"booking_id": rows[1]["id"], "start_date": "2026-11-22", "end_date": "2026-11-25", "start_minute": 900, "end_minute": 1080},
    ]
    with client:
        response = client.get(f"/event-requests/{event}/change-requests/{change}/booking-plan", headers=headers("coord-1"))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "event_request_id": event, "change_request_id": change, "event_updated_at": "2026-10-22T01:00:00Z",
        "bookings": current, "automatic_plan": None if manual else automatic,
        "automatic_plan_error": "unsupported_date_mapping" if manual else None,
    }
    assert repository.preview_calls == [("change", event, change), ("bookings", event)]
    assert protected(repository) == before
    assert deepcopy(repository.change_request_rows) == before["change_request_rows"]
