"""SCRUM-20 agreed timing-change cause: reader compatibility, not the venue writer."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_arrangement_reviews import (
    COORDINATOR,
    EVENT,
    fixture,
    normalized,
    review,
    snapshot,
)
from test_organisation_access import client_for

from app.models.arrangement_review import ArrangementReviewResponse


def timing_review():
    return review(
        20,
        trigger_type="venue_timing_change",
        changed_fields=["setup_minutes", "turnaround_minutes"],
        reason="Venue setup changed from 0 to 30 minutes; booking padding now conflicts.",
    )


# AC6-X1 (cross-cutting): the current coordinator must retain complete outstanding evidence when a valid fourth cause reaches the real response model.
def test_current_coordinator_reads_venue_timing_cause_without_state_changes():
    repository, assignments = fixture()
    expected = timing_review()
    repository.arrangement_review_rows = [deepcopy(expected)]
    before = snapshot(repository)
    application = client_for(repository, COORDINATOR, ("event_coordinator",), assignments).app
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert response.status_code == 200, response.text
    assert normalized(response.json()) == normalized([expected])
    assert repository.read_calls == [EVENT]
    assert snapshot(repository) == before


# AC6-N1 (negative): accepting the named fourth cause must not turn cause validation into acceptance of arbitrary strings.
def test_unrecognised_review_cause_remains_a_specific_model_failure():
    invalid = {**timing_review(), "trigger_type": "not_a_review_cause"}
    before = deepcopy(invalid)
    with pytest.raises(ValidationError) as caught:
        ArrangementReviewResponse.model_validate(invalid)
    errors = caught.value.errors()
    assert [(error["loc"], error["type"], error["input"]) for error in errors] == [
        (("trigger_type",), "literal_error", "not_a_review_cause"),
    ]
    assert invalid == before
