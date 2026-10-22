"""SCRUM-35 rejection-only API contract; fake persistence is not PostgreSQL proof."""

from copy import deepcopy
from datetime import datetime

import pytest
from test_event_change_request import change_payload, eligible_fixture
from test_event_transition_controller import headers

REASON = "The booked arrangements cannot accommodate the requested attendance."


def comparable_change(row):
    # Compare aware timestamp instants, preserving every other field exactly.
    return {
        key: datetime.fromisoformat(value) if key in {"created_at", "base_event_updated_at", "decided_at"} and value is not None else value
        for key, value in row.items()
    }


def create_pending(client, event_id):
    response = client.post(
        f"/event-requests/{event_id}/change-requests",
        headers=headers("organiser-1"), json=change_payload(),
    )
    assert response.status_code == 201
    return response.json()


def reject(client, event_id, change_id, reason=REASON):
    return client.post(
        f"/event-requests/{event_id}/change-requests/{change_id}/decision",
        headers=headers("coord-1"), json={"decision": "Rejected", "reason": reason},
    )


@pytest.mark.parametrize("status", ["Approved", "Planning"], ids=["AC4-H1", "AC4-P1"])
# AC4-H1, AC4-P1 (partition): rejecting a proposal retains its complete audit and owner-visible history without applying either eligible plan.
def test_assigned_coordinator_rejects_and_owner_reads_unchanged_plan(status):
    client, events, event_id = eligible_fixture(status)
    with client:
        pending = create_pending(client, event_id)
        before = deepcopy(events.rows)
        response = reject(client, event_id, pending["id"])
        assert response.status_code == 200
        rejected = response.json()
        assert rejected == {
            **pending, "status": "Rejected", "coordinator_id": "coord-1",
            "decision_reason": REASON, "decided_at": rejected["decided_at"],
        }
        assert rejected["decided_at"] is not None
        assert datetime.fromisoformat(rejected["decided_at"]).utcoffset() is not None
        assert [comparable_change(row) for row in events.change_request_rows] == [comparable_change(rejected)]
        assert events.rows == before
        listing = client.get(
            f"/event-requests/{event_id}/change-requests", headers=headers("organiser-1"),
        )
        assert listing.status_code == 200
        assert listing.json() == [rejected]
        assert events.rows == before


# AC5-N4 (negative): a repeated rejection cannot replace the first coordinator/reason/time or active plan.
def test_repeated_rejection_preserves_first_outcome():
    client, events, event_id = eligible_fixture()
    with client:
        pending = create_pending(client, event_id)
        first = reject(client, event_id, pending["id"])
        assert first.status_code == 200
        before = deepcopy((events.rows, events.change_request_rows))
        repeated = reject(client, event_id, pending["id"], "Replacement reason must not be saved.")
        assert repeated.status_code == 409
        assert repeated.json() == {"detail": f"Event request {event_id} cannot accept that change action"}
        assert deepcopy((events.rows, events.change_request_rows)) == before


# AC4-N2 (negative): an unknown proposal UUID cannot be used to reject the current pending request.
def test_unknown_proposal_is_not_rejected_and_current_state_is_preserved():
    client, events, event_id = eligible_fixture()
    with client:
        create_pending(client, event_id)
        before = deepcopy((events.rows, events.change_request_rows))
        response = reject(client, event_id, "35000000-0000-4000-8000-000000000099")
        assert response.status_code == 404
        assert response.json() == {"detail": "Change request not found"}
        assert deepcopy((events.rows, events.change_request_rows)) == before
