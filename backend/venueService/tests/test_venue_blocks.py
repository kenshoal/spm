"""Block creation through the API, including storage and caller identity."""

from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.block_repository import block_repository
from app.dependencies import Principal, require_venue_staff
from app.main import app

client = TestClient(app)


def payload(**overrides: object) -> dict:
    data = {
        "start_date": "2026-09-20",
        "end_date": "2026-09-21",
        "slots": ["PM", "AM"],
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
    assert body["slots"] == ["AM", "PM"]
    assert body["reason_category"] == "maintenance"
    assert body["reason_detail"] == "Air-conditioning repairs"
    assert block_repository.get(body["id"]).model_dump(mode="json") == body
    assert client.get(f"/venues/{venue_id}").json()["status"] == "available"


def test_missing_venue_does_not_store_block():
    response = client.post("/venues/missing/blocks", json=payload())
    assert response.status_code == 404
    assert response.json()["detail"] == "Venue not found"
    assert block_repository.list() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"end_date": "2026-09-19"},
        {"start_date": "not-a-date"},
        {"slots": []},
        {"slots": ["AM", "AM"]},
        {"slots": [None]},
        {"slots": ["AFTERNOON"]},
        {"reason_category": "unknown"},
        {"reason_detail": "x" * 1001},
        {"created_by": "spoofed-staff"},
        {"venue_id": "another-venue"},
        {"status": "lifted"},
        {"id": "client-supplied"},
        {"created_at": "2026-09-20T00:00:00Z"},
    ],
)
def test_invalid_request_does_not_store_block(venue_id, changes):
    response = client.post(f"/venues/{venue_id}/blocks", json=payload(**changes))
    assert response.status_code == 422
    assert block_repository.list() == []


def test_multiple_blocks_have_distinct_ids_and_optional_detail(venue_id):
    data = payload(slots=["NIGHT"])
    del data["reason_detail"]
    responses = [
        client.post(f"/venues/{venue_id}/blocks", json=data) for _ in range(2)
    ]
    assert all(response.status_code == 201 for response in responses)
    first, second = [response.json() for response in responses]
    assert first["id"] != second["id"]
    assert first["reason_detail"] is None
    assert len(block_repository.list()) == 2
