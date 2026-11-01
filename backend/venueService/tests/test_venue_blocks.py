"""Block creation through the API, including storage and caller identity."""

from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.block_repository import block_repository
from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)


def payload(**overrides: object) -> dict:
    data = {
        "start_date": "2026-09-20",
        "end_date": "2026-09-21",
        # 07:00-18:00, the old AM and PM slots (SCRUM-65).
        "start_minute": 420,
        "end_minute": 1080,
        "reason_category": "maintenance",
        "reason_detail": " Air-conditioning repairs ",
    }
    return data | overrides


@pytest.fixture
def venue_id() -> str:
    response = client.post(
        "/venues",
        json={"name": "Orchard Hall", "location": "Orchard", "max_capacity": 100},
    )
    assert response.status_code == 201
    return response.json()["id"]


# AC1-H5 (happy): the API stores a normalised block with server-set id, creator and status
def test_create_block_stores_normalized_record_and_server_metadata(venue_id):
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_venue_staff] = lambda: Principal(
        user_id="test-staff", roles=("venue_staff",)
    )
    try:
        response = client.post(f"/venues/{venue_id}/blocks", json=payload())
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    assert body["venue_id"] == venue_id
    assert body["created_by"] == "test-staff"
    assert body["status"] == "active"
    assert body["start_date"] == "2026-09-20"
    assert body["end_date"] == "2026-09-21"
    assert (body["start_minute"], body["end_minute"]) == (420, 1080)
    assert body["slots"] == ["AM", "PM"]
    assert body["reason_category"] == "maintenance"
    assert body["reason_detail"] == "Air-conditioning repairs"
    assert block_repository.get(body["id"]).model_dump(mode="json") == body
    assert client.get(f"/venues/{venue_id}").json()["status"] == "available"


# AC1-P6e, AC1-P6f (partition): the Week 7 change 2 reasons "equipment failure" and "other" are accepted
@pytest.mark.parametrize("reason", ["equipment_failure", "other"])
def test_create_block_accepts_equipment_failure_and_other(venue_id, reason):
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_venue_staff] = lambda: Principal(
        user_id="test-staff", roles=("venue_staff",)
    )
    try:
        response = client.post(
            f"/venues/{venue_id}/blocks", json=payload(reason_category=reason)
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 201
    assert response.json()["reason_category"] == reason


# AC1-X2 (cross-cutting): a non-Venue-Staff caller is refused and no block is stored
def test_non_venue_staff_cannot_create_block(venue_id):
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000002",
        roles=("event_coordinator",),
    )
    app.dependency_overrides.pop(require_venue_staff, None)

    response = client.post(f"/venues/{venue_id}/blocks", json=payload())

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    assert block_repository.list() == []


# AC1-N14 (negative): a block for an unknown venue is refused and nothing is stored
def test_missing_venue_does_not_store_block():
    response = client.post("/venues/missing/blocks", json=payload())
    assert response.status_code == 404
    assert response.json()["detail"] == "Venue not found"
    assert block_repository.list() == []


# AC1-N15 (negative): an invalid or spoofed block request is refused and nothing is stored
@pytest.mark.parametrize(
    "changes",
    [
        {"end_date": "2026-09-19"},
        {"start_date": "not-a-date"},
        # Times replace slots (SCRUM-65); the slots field itself is refused.
        {"start_minute": 430},
        {"end_minute": 420},
        {"start_minute": None},
        {"slots": ["AM"]},
        {"reason_category": "unknown"},
        {"reason_detail": "x" * 1001},
        {"created_by": "spoofed-staff"},
        {"venue_id": "another-venue"},
        {"status": "lifted"},
        {"id": "client-supplied"},
        {"created_at": "2026-09-20T00:00:00Z"},
    ],
    ids=["AC1-N15a", "AC1-N15b", "AC1-N15c", "AC1-N15d", "AC1-N15e", "AC1-N15f", "AC1-N15g", "AC1-N15h", "AC1-N15i", "AC1-N15j", "AC1-N15k", "AC1-N15l", "AC1-N15m"],
)
def test_invalid_request_does_not_store_block(venue_id, changes):
    response = client.post(f"/venues/{venue_id}/blocks", json=payload(**changes))
    assert response.status_code == 422
    assert block_repository.list() == []


# AC1-P8 (partition): repeated blocks get distinct ids and detail is optional
def test_multiple_blocks_have_distinct_ids_and_optional_detail(venue_id):
    data = payload(start_minute=1080, end_minute=1440)
    del data["reason_detail"]
    responses = [
        client.post(f"/venues/{venue_id}/blocks", json=data) for _ in range(2)
    ]
    assert all(response.status_code == 201 for response in responses)
    first, second = [response.json() for response in responses]
    assert first["id"] != second["id"]
    assert first["reason_detail"] is None
    assert len(block_repository.list()) == 2


def signed_in_as(role: str) -> None:
    """Replace the conftest Venue Staff caller with a verified user of one role."""
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000003", roles=(role,)
    )
    app.dependency_overrides.pop(require_venue_staff, None)


# AC1-X4 (cross-cutting): internal block reasons are readable by Venue Staff only
@pytest.mark.parametrize(
    "role", ["event_coordinator", "event_organiser", "attendee"],
    ids=["AC1-X4a", "AC1-X4b", "AC1-X4c"],
)
def test_only_venue_staff_can_list_block_reasons(venue_id, role):
    assert client.post(f"/venues/{venue_id}/blocks", json=payload()).status_code == 201
    signed_in_as(role)

    response = client.get(f"/venues/{venue_id}/blocks")

    assert response.status_code == 403
    assert "Air-conditioning" not in response.text
    assert len(block_repository.list()) == 1


# AC2-X1 (cross-cutting): only Venue Staff and Event Coordinators may check availability
@pytest.mark.parametrize(
    "role,expected",
    [("venue_staff", 200), ("event_coordinator", 200), ("event_organiser", 403), ("attendee", 403)],
    ids=["AC2-X1a", "AC2-X1b", "AC2-X1c", "AC2-X1d"],
)
def test_availability_check_is_limited_to_internal_planners(venue_id, role, expected):
    signed_in_as(role)

    response = client.post(
        f"/venues/{venue_id}/availability",
        json={"start_date": "2026-09-20", "end_date": "2026-09-20", "start_minute": 420,
              "end_minute": 720},
    )

    assert response.status_code == expected
