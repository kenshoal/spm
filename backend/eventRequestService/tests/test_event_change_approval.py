"""Approved non-date SCRUM35 scope; injected persistence is not native atomicity proof."""

from copy import deepcopy
from datetime import datetime

import pytest
from test_event_change_rejection import comparable_change
from test_event_change_request import eligible_fixture
from test_event_transition_controller import headers

CHANGES = {
    "expected_attendance": 80,
    "venue_requirements": "Larger seminar room with step-free access",
    "equipment_requirements": "Two wireless microphones",
}


def create_nondate_pending(client, event_id, **changes):
    response = client.post(
        f"/event-requests/{event_id}/change-requests",
        headers=headers("organiser-1"),
        json={"explanation": "The approved activity now needs the recorded non-date arrangements.", **(changes or CHANGES)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, event_id, change_id):
    return client.post(
        f"/event-requests/{event_id}/change-requests/{change_id}/decision",
        headers=headers("coord-1"), json={"decision": "Approved"},
    )


@pytest.mark.parametrize("status", ["Approved", "Planning"], ids=["AC3-H1", "AC3-P1"])
# AC3-H1, AC3-P1 (partition): either eligible event can apply an exact non-date proposal with complete retained approval evidence and no unrelated plan changes.
def test_current_coordinator_approves_nondate_change_and_owner_reads_saved_outcome(status):
    client, events, event_id = eligible_fixture(status)
    with client:
        pending = create_nondate_pending(client, event_id)
        assert pending["proposed_changes"] == CHANGES
        before = deepcopy(events.rows)
        response = approve(client, event_id, pending["id"])
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved == {
            **pending, "status": "Approved", "coordinator_id": "coord-1",
            "decision_reason": None, "decided_at": saved["decided_at"],
        }
        assert saved["decided_at"] is not None
        assert datetime.fromisoformat(saved["decided_at"]).utcoffset() is not None
        assert [comparable_change(row) for row in events.change_request_rows] == [comparable_change(saved)]
        after = deepcopy(events.rows)
        updated_at = after[event_id]["updated_at"]
        assert datetime.fromisoformat(updated_at).utcoffset() is not None
        assert updated_at != before[event_id]["updated_at"]
        expected = deepcopy(before)
        expected[event_id].update({**CHANGES, "updated_at": updated_at})
        assert after == expected
        owner = client.get(f"/event-requests/{event_id}/change-requests", headers=headers("organiser-1"))
        assert owner.status_code == 200
        assert owner.json() == [saved]
        assert events.rows == after


# AC1-P3, AC3-P2 (partition): accessibility needs are a supported value (SCRUM-35 AC1): an organiser can
# propose them alone, the Coordinator can approve them, and the event stores the new text
def test_an_accessibility_only_proposal_can_be_made_and_approved():
    changes = {"accessibility_needs": "Step-free access and a hearing loop"}
    client, events, event_id = eligible_fixture("Planning")
    with client:
        pending = create_nondate_pending(client, event_id, **changes)
        assert pending["proposed_changes"] == changes
        response = approve(client, event_id, pending["id"])

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Approved"
    assert events.rows[event_id]["accessibility_needs"] == "Step-free access and a hearing loop"


# AC1-N3 (negative): a blank accessibility proposal is refused like any other blank value
def test_a_blank_accessibility_proposal_is_refused():
    client, events, event_id = eligible_fixture("Planning")
    before = deepcopy(events.rows)
    with client:
        response = client.post(
            f"/event-requests/{event_id}/change-requests",
            headers=headers("organiser-1"),
            json={"explanation": "No longer needed", "accessibility_needs": "   "},
        )

    assert response.status_code == 422
    assert events.rows == before
