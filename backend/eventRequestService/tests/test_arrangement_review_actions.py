"""SCRUM-64 domain queues/clear HTTP contract; real mutation SQL is separate."""

from copy import deepcopy
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_arrangement_reviews import (
    EVENT,
    OTHER_EVENT,
    ArrangementReviewRepository,
    fixture,
    snapshot,
)
from test_organisation_access import client_for

from app.main import create_app
from app.repositories import EventRequestRpcError, SupabaseRepositoryError

VENUE_STAFF = "64000000-0000-4000-8000-000000000001"
TECH_STAFF = "64000000-0000-4000-8000-000000000002"
COORDINATOR = "64000000-0000-4000-8000-000000000003"
MISSING = "64000000-0000-4000-8000-000000000099"
CLEARED_TIME = "2026-10-15T03:00:00Z"


class DomainReviewRepository(ArrangementReviewRepository):
    """Raw query/RPC outcomes only: no permission, clear or stale-state rules."""

    def __init__(self) -> None:
        super().__init__()
        self.clear_calls: list[tuple] = []
        self.queue_calls: list[str] = []
        self.get_calls: list[str] = []
        self.clear_result: dict[str, Any] | None = None
        self.clear_error: Exception | None = None
        self.queue_error: Exception | None = None

    def list_arrangement_reviews_for_arrangement(self, arrangement: str) -> list[dict]:
        self.queue_calls.append(arrangement)
        if self.queue_error is not None:
            raise self.queue_error
        return deepcopy(
            [
                row
                for row in self.arrangement_review_rows
                if row["arrangement"] == arrangement
            ]
        )

    def get_arrangement_review(self, review_id: str) -> dict | None:
        self.get_calls.append(review_id)
        return next(
            (
                deepcopy(row)
                for row in self.arrangement_review_rows
                if row["id"] == review_id
            ),
            None,
        )

    def clear_arrangement_review(
        self, review_id: str, actor_id: str, *args, **kwargs
    ) -> dict:
        self.clear_calls.append((review_id, actor_id, args, kwargs))
        if self.clear_error is not None:
            raise self.clear_error
        assert self.clear_result is not None, "fixture: configure concrete RPC result"
        return deepcopy(self.clear_result)


def action_fixture():
    seeded, assignments = fixture()
    repository = DomainReviewRepository()
    repository.__dict__.update(deepcopy(vars(seeded)))
    repository.rows[OTHER_EVENT] = {**repository.rows[EVENT], "id": OTHER_EVENT}
    return repository, assignments


def protected(repository: DomainReviewRepository):
    # Prepared transport outcomes/call observations are fixture instrumentation.
    return {
        key: value
        for key, value in snapshot(repository).items()
        if key
        not in {
            "clear_calls",
            "queue_calls",
            "get_calls",
            "clear_result",
            "clear_error",
            "queue_error",
        }
    }


def evidence(row: dict) -> dict:
    return {
        **row,
        "raised_at": datetime.fromisoformat(row["raised_at"]),
        "cleared_at": datetime.fromisoformat(row["cleared_at"])
        if row["cleared_at"]
        else None,
    }


def error(response, status: int, code: str):
    assert response.status_code == status
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("code") == code
    for private in (
        "Attendance changed",
        "microphone",
        "trigger_id",
        "internal_storage_detail",
    ):
        assert private not in response.text


@pytest.mark.parametrize(
    ("arrangement", "role", "actor", "row_index", "expected_ids"),
    [
        ("venue_booking", "venue_staff", VENUE_STAFF, 4, [1, 9, 3]),
        ("equipment_reservation", "technical_support", TECH_STAFF, 0, [2]),
    ],
    ids=["AC4-H1", "AC4-P1"],
)
# AC4-H1, AC4-P1 (partition): either responsible domain can review its queue and clear using the current staff identity.
def test_domain_staff_gets_outstanding_queue_and_complete_clear_result(
    arrangement,
    role,
    actor,
    row_index,
    expected_ids,
):
    repository, assignments = action_fixture()
    original = deepcopy(repository.arrangement_review_rows[row_index])
    repository.clear_result = {
        **original,
        "cleared_at": CLEARED_TIME,
        "cleared_by": actor,
    }
    expected = [
        deepcopy(
            next(
                row
                for row in repository.arrangement_review_rows
                if row["id"].endswith(f"{number:012d}")
            )
        )
        for number in expected_ids
    ]
    before = protected(repository)
    with client_for(repository, actor, (role,), assignments) as client:
        queued = client.get("/arrangement-reviews", params={"arrangement": arrangement})
        assert queued.status_code == 200
        assert [evidence(row) for row in queued.json()] == [
            evidence(row) for row in expected
        ]
        cleared = client.post(f"/arrangement-reviews/{original['id']}/clear")
    assert cleared.status_code == 200
    assert evidence(cleared.json()) == evidence(repository.clear_result)
    assert datetime.fromisoformat(cleared.json()["cleared_at"]).utcoffset() is not None
    assert [(call[0], call[1]) for call in repository.clear_calls] == [
        (original["id"], actor)
    ]
    assert protected(repository) == before


@pytest.mark.parametrize(
    ("actor", "roles"),
    [(VENUE_STAFF, ("venue_staff",)), (COORDINATOR, ("event_coordinator",))],
    ids=["AC4-N1", "AC4-P2"],
)
# AC4-N1, AC4-P2 (partition): another domain or coordinator capability cannot replace the required domain staff role.
def test_wrong_domain_or_role_cannot_read_queue_or_clear(actor, roles):
    repository, assignments = action_fixture()
    target = repository.arrangement_review_rows[0]  # equipment, not venue
    repository.clear_error = EventRequestRpcError("Forbidden", errcode="P0003")
    before = protected(repository)
    with client_for(repository, actor, roles, assignments) as client:
        queued = client.get(
            "/arrangement-reviews", params={"arrangement": "equipment_reservation"}
        )
        cleared = client.post(f"/arrangement-reviews/{target['id']}/clear")
    error(queued, 403, "ARRANGEMENT_REVIEW_FORBIDDEN")
    error(cleared, 403, "ARRANGEMENT_REVIEW_FORBIDDEN")
    assert protected(repository) == before


# AC4-N2 (negative): an authoritative repeated-clear refusal must remain a conflict without altering stored evidence.
def test_repeated_clear_maps_locked_refusal_without_side_effects():
    repository, assignments = action_fixture()
    target = repository.arrangement_review_rows[4]
    repository.clear_error = EventRequestRpcError("Already cleared", errcode="P0004")
    before = protected(repository)
    with client_for(repository, VENUE_STAFF, ("venue_staff",), assignments) as client:
        response = client.post(f"/arrangement-reviews/{target['id']}/clear")
    error(response, 409, "ARRANGEMENT_REVIEW_ALREADY_CLEARED")
    assert protected(repository) == before


# AC4-N3 (negative): missing review identity cannot expose metadata or mutate another review.
def test_missing_review_is_a_specific_not_found():
    repository, assignments = action_fixture()
    repository.clear_error = EventRequestRpcError("Missing", errcode="P0002")
    before = protected(repository)
    with client_for(repository, VENUE_STAFF, ("venue_staff",), assignments) as client:
        response = client.post(f"/arrangement-reviews/{MISSING}/clear")
    error(response, 404, "ARRANGEMENT_REVIEW_NOT_FOUND")
    assert protected(repository) == before


# AC4-N4 (negative): both queue and clear require a verified session before protected storage.
def test_domain_queue_and_clear_require_authentication():
    repository, assignments = action_fixture()
    before = protected(repository)
    with TestClient(create_app(repository, assignments)) as client:
        queued = client.get(
            "/arrangement-reviews", params={"arrangement": "venue_booking"}
        )
        cleared = client.post(
            f"/arrangement-reviews/{repository.arrangement_review_rows[4]['id']}/clear"
        )
    for response in (queued, cleared):
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}
    assert repository.clear_calls == []
    assert repository.queue_calls == []
    assert repository.get_calls == []
    assert protected(repository) == before


# AC4-N5 (negative): read/clear transport failures expose a safe outage rather than internal details or false success.
def test_queue_and_clear_outages_are_safe_and_nonmutating():
    repository, assignments = action_fixture()
    repository.queue_error = SupabaseRepositoryError(
        "internal_storage_detail queue relation"
    )
    repository.clear_error = SupabaseRepositoryError(
        "internal_storage_detail clear relation"
    )
    before = protected(repository)
    with client_for(repository, VENUE_STAFF, ("venue_staff",), assignments) as client:
        queued = client.get(
            "/arrangement-reviews", params={"arrangement": "venue_booking"}
        )
        cleared = client.post(
            f"/arrangement-reviews/{repository.arrangement_review_rows[4]['id']}/clear"
        )
    for response in (queued, cleared):
        assert response.status_code == 502
        assert response.json() == {"detail": "Arrangement reviews unavailable"}
    assert protected(repository) == before


# AC5-N4 (negative): omitting the domain cannot silently widen a staff queue into event-wide access.
def test_domain_query_is_required_before_storage():
    repository, assignments = action_fixture()
    before = protected(repository)
    with client_for(repository, VENUE_STAFF, ("venue_staff",), assignments) as client:
        response = client.get("/arrangement-reviews")
    assert response.status_code == 422
    assert any(
        item["loc"] == ["query", "arrangement"] and item["type"] == "missing"
        for item in response.json()["detail"]
    )
    assert repository.queue_calls == []
    assert repository.get_calls == []
    assert repository.clear_calls == []
    assert protected(repository) == before
