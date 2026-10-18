"""SCRUM-64 AC5 HTTP contract; repository/Auth dependencies are local doubles."""

from copy import deepcopy
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_event_request_controller import FakeCoordinatorAssignmentRepository
from test_organisation_access import A1, OrganisationFakeRepository, client_for

from app.main import create_app
from app.repositories import SupabaseRepositoryError

EVENT = "eeeeeeee-1111-4111-8111-111111111111"
OTHER_EVENT = "eeeeeeee-2222-4222-8222-222222222222"
COORDINATOR = "cccccccc-1111-4111-8111-111111111111"
REPLACEMENT = "cccccccc-2222-4222-8222-222222222222"
NOW = "2026-10-15T01:00:00Z"


class ArrangementReviewRepository(OrganisationFakeRepository):
    """Raw storage double: never decides permissions, outstanding state or order."""

    def __init__(self) -> None:
        super().__init__()
        self.arrangement_review_rows: list[dict[str, Any]] = []
        self.history_rows = [{"event_request_id": EVENT, "new_status": "Planning"}]
        self.booking_rows = [{"id": "booking", "status": "Approved"}]
        self.reservation_rows = [{"id": "reservation", "status": "Reserved"}]
        self.notification_rows = [{"id": "existing-notification", "delivered": False}]
        self.read_calls: list[str] = []
        self.fail_reads = False

    def list_arrangement_reviews(self, event_request_id: str) -> list[dict[str, Any]]:
        self.read_calls.append(event_request_id)
        if self.fail_reads:
            raise SupabaseRepositoryError(
                "internal_storage_detail: private review relation unreachable"
            )
        return deepcopy(
            [
                row
                for row in self.arrangement_review_rows
                if row["event_request_id"] == event_request_id
            ]
        )


def review(number: int, **overrides: Any) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-4000-8000-{number:012d}",
        "event_request_id": EVENT,
        "arrangement": "venue_booking",
        "arrangement_id": "bbbbbbbb-1111-4111-8111-111111111111",
        "trigger_id": f"11111111-1111-4111-8111-{number:012d}",
        "trigger_type": "event_change",
        "changed_fields": ["expected_attendance"],
        "reason": f"Attendance changed; review {number}",
        "raised_at": NOW,
        "cleared_at": None,
        "cleared_by": None,
        **overrides,
    }


def fixture():
    repository = ArrangementReviewRepository()
    repository.rows[EVENT] = {
        "id": EVENT,
        "organiser_id": A1,
        "event_name": "SCRUM-64 review fixture",
        "status": "Planning",
        "created_at": NOW,
        "updated_at": NOW,
    }
    # Deliberately mixed: cleared, other event, reversed ties and different domains.
    repository.arrangement_review_rows = [
        review(
            2,
            arrangement="equipment_reservation",
            arrangement_id="dddddddd-1111-4111-8111-111111111111",
            trigger_type="equipment_unavailable",
            changed_fields=[],
            reason="Reserved microphone unavailable",
        ),
        review(9, event_request_id=OTHER_EVENT),
        review(4, cleared_at="2026-10-15T02:00:00Z", cleared_by="venue-staff"),
        review(
            3,
            trigger_type="safety_recheck",
            changed_fields=[],
            reason="Safety officer requests venue recheck",
        ),
        review(
            1,
            raised_at="2026-10-14T23:30:00-02:00",
            changed_fields=["proposed_date_times", "expected_attendance"],
        ),
    ]
    assignments = FakeCoordinatorAssignmentRepository(repository)
    assignments.rows.append(
        {
            "id": 1,
            "event_request_id": EVENT,
            "coordinator_id": COORDINATOR,
            "assigned_by": "operations-manager",
            "assigned_at": NOW,
        }
    )
    return repository, assignments


def snapshot(repository: ArrangementReviewRepository) -> dict[str, Any]:
    return deepcopy(
        {
            key: value
            for key, value in vars(repository).items()
            if key not in {"read_calls", "fail_reads"}
        }
    )


def normalized(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "raised_at": datetime.fromisoformat(row["raised_at"]),
        }
        for row in rows
    ]


def assert_private_failure(response, status: int, code: str) -> None:
    assert response.status_code == status
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("code") == code
    for protected in (
        "Attendance changed",
        "microphone",
        "arrangement_id",
        "trigger_id",
    ):
        assert protected not in response.text


# AC5-H1 (happy): the current coordinator sees complete outstanding evidence without cleared or cross-event leakage.
def test_current_coordinator_reads_outstanding_reviews_in_deterministic_order():
    repository, assignments = fixture()
    before = snapshot(repository)
    expected = [
        deepcopy(repository.arrangement_review_rows[index]) for index in (4, 3, 0)
    ]
    with client_for(
        repository, COORDINATOR, ("event_coordinator",), assignments
    ) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert normalized(response.json()) == normalized(expected)
    assert repository.read_calls == [EVENT]
    assert all(
        datetime.fromisoformat(row["raised_at"]).utcoffset() is not None
        for row in response.json()
    )
    assert snapshot(repository) == before


# AC5-B1 (boundary): cleared records do not turn an empty outstanding queue into false work.
def test_no_outstanding_reviews_returns_an_empty_list():
    repository, assignments = fixture()
    repository.arrangement_review_rows = [repository.arrangement_review_rows[2]]
    before = snapshot(repository)
    with client_for(
        repository, COORDINATOR, ("event_coordinator",), assignments
    ) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert response.status_code == 200
    assert response.json() == []
    assert snapshot(repository) == before


@pytest.mark.parametrize(
    ("caller", "roles"),
    [(A1, ("event_organiser",)), ("venue-staff", ("venue_staff",))],
    ids=["AC5-P1", "AC5-P2"],
)
# AC5-P1, AC5-P2 (partition): ownership or domain staff capability must not widen the coordinator-wide read boundary.
def test_noncoordinator_roles_cannot_read_event_wide_reviews(caller, roles):
    repository, assignments = fixture()
    before = snapshot(repository)
    with client_for(repository, caller, roles, assignments) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert_private_failure(response, 403, "ARRANGEMENT_REVIEWS_FORBIDDEN")
    assert repository.read_calls == []
    assert snapshot(repository) == before


# AC5-N1 (negative): a coordinator with no current relationship cannot distinguish an existing request from a missing one.
def test_unrelated_coordinator_gets_private_not_found():
    repository, assignments = fixture()
    before = snapshot(repository)
    with client_for(
        repository, REPLACEMENT, ("event_coordinator",), assignments
    ) as client:
        existing = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
        missing = client.get(f"/event-requests/{OTHER_EVENT}/arrangement-reviews")
    assert_private_failure(existing, 404, "ARRANGEMENT_REVIEWS_NOT_FOUND")
    assert missing.status_code == 404
    assert existing.json() == missing.json()
    assert repository.read_calls == []
    assert snapshot(repository) == before


# AC5-X1 (cross-cutting): a previously permitted coordinator loses access as soon as the current assignment changes.
def test_reassignment_uses_current_coordinator_instead_of_historical_access():
    repository, assignments = fixture()
    with client_for(
        repository, COORDINATOR, ("event_coordinator",), assignments
    ) as former:
        initial = former.get(f"/event-requests/{EVENT}/arrangement-reviews")
        assert initial.status_code == 200
        assignments.rows.append(
            {
                "id": 2,
                "event_request_id": EVENT,
                "coordinator_id": REPLACEMENT,
                "assigned_by": "operations-manager",
                "assigned_at": "2026-10-15T03:00:00Z",
            }
        )
        before = snapshot(repository)
        refused = former.get(f"/event-requests/{EVENT}/arrangement-reviews")
    with client_for(
        repository, REPLACEMENT, ("event_coordinator",), assignments
    ) as current:
        allowed = current.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert_private_failure(refused, 404, "ARRANGEMENT_REVIEWS_NOT_FOUND")
    assert allowed.status_code == 200
    assert allowed.json() == initial.json()
    assert snapshot(repository) == before


# AC5-N2 (negative): unauthenticated reads stop before protected review storage is queried.
def test_arrangement_review_list_requires_authentication():
    repository, assignments = fixture()
    before = snapshot(repository)
    with TestClient(create_app(repository, assignments)) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert repository.read_calls == []
    assert snapshot(repository) == before


# AC5-N3 (negative): a repository outage must not become an apparently clear readiness queue.
def test_review_repository_failure_is_not_an_empty_success():
    repository, assignments = fixture()
    repository.fail_reads = True
    before = snapshot(repository)
    with client_for(
        repository, COORDINATOR, ("event_coordinator",), assignments
    ) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert response.status_code == 502
    assert response.json() == {"detail": "Arrangement reviews unavailable"}
    assert snapshot(repository) == before
