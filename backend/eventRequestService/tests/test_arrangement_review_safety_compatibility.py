"""SCRUM-64 compatibility with SCRUM-60's approved Safety Review state."""

from copy import deepcopy

from fastapi.testclient import TestClient
from test_arrangement_reviews import (
    COORDINATOR,
    EVENT,
    REPLACEMENT,
    assert_private_failure,
    fixture,
    normalized,
    snapshot,
)
from test_organisation_access import client_for


# AC5-P3 (partition): Safety Review remains readable by its current coordinator without lifecycle or resource writes.
def test_assigned_coordinator_reads_safety_review_outstanding_evidence():
    repository, assignments = fixture()
    expected = [deepcopy(repository.arrangement_review_rows[i]) for i in (4, 3, 0)]
    application = client_for(
        repository, COORDINATOR, ("event_coordinator",), assignments
    ).app
    with TestClient(application, raise_server_exceptions=False) as client:
        control = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
        assert control.status_code == 200
        assert normalized(control.json()) == normalized(expected)
        repository.rows[EVENT]["status"] = "Safety Review"
        repository.history_rows[-1]["new_status"] = "Safety Review"
        before = snapshot(repository)
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert response.status_code == 200, response.text
    assert normalized(response.json()) == normalized(expected)
    assert repository.read_calls == [EVENT, EVENT]
    assert snapshot(repository) == before


# AC5-P4 (partition): Safety Officer capability does not confer current-coordinator review visibility.
def test_safety_officer_only_cannot_read_event_wide_reviews():
    repository, assignments = fixture()
    repository.rows[EVENT]["status"] = "Safety Review"
    before = snapshot(repository)
    with client_for(
        repository, "safety-officer-only", ("safety_officer",), assignments
    ) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert_private_failure(response, 403, "ARRANGEMENT_REVIEWS_FORBIDDEN")
    assert repository.read_calls == []
    assert snapshot(repository) == before


# AC5-P5 (partition): entering Safety Review never widens access to an unassigned coordinator.
def test_unassigned_coordinator_cannot_read_safety_review_evidence():
    repository, assignments = fixture()
    repository.rows[EVENT]["status"] = "Safety Review"
    before = snapshot(repository)
    application = client_for(
        repository, REPLACEMENT, ("event_coordinator",), assignments
    ).app
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert_private_failure(response, 404, "ARRANGEMENT_REVIEWS_NOT_FOUND")
    assert repository.read_calls == []
    assert snapshot(repository) == before
