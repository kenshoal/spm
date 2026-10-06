import pytest
from fastapi.testclient import TestClient

from app.block_models import BlockStatus
from app.block_repository import block_repository
from app.main import app

client = TestClient(app)


@pytest.fixture
def venue():
    result = client.post(
        "/venues", json={"name": "Hall", "location": "Campus", "max_capacity": 50}
    )
    assert result.status_code == 201
    return result.json()["id"]


def make_block(venue, **overrides):
    response = client.post(
        f"/venues/{venue}/blocks",
        json={
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "slots": ["AM"],
            "reason_category": "maintenance",
        }
        | overrides,
    )
    assert response.status_code == 201
    return response.json()["id"]


def check(venue, **overrides):
    return client.post(
        f"/venues/{venue}/availability",
        json={
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "slots": ["AM"],
        }
        | overrides,
    )


# AC2-H3 (happy): the availability check reports block conflicts and writes nothing
def test_availability_flow_reports_conflicts_without_writes(venue):
    assert check(venue).json()["available"] is True
    block = make_block(venue)
    result = check(
        venue, start_date="2026-09-30", end_date="2026-10-02", slots=["AM", "PM"]
    )
    assert result.status_code == 200
    assert result.json() == {
        "venue_id": venue,
        "available": False,
        "reasons": ["active_block"],
        "unsupported_slots": [],
        "conflicts": [
            {
                "block_id": block,
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "slots": ["AM"],
            }
        ],
    }
    assert len(block_repository.list()) == 1
    assert check(venue, slots=["PM"]).json()["available"] is True
    block_repository.get(block).status = BlockStatus.LIFTED
    assert check(venue).json()["available"] is True


# AC2-B6 (boundary): the availability check treats block dates as inclusive
@pytest.mark.parametrize(
    "day,available",
    [
        ("2026-09-30", True),
        ("2026-10-01", False),
        ("2026-10-03", False),
        ("2026-10-04", True),
    ],
    ids=["AC2-B6a", "AC2-B6b", "AC2-B6c", "AC2-B6d"],
)
def test_availability_inclusive_boundaries(venue, day, available):
    make_block(venue)
    assert check(venue, start_date=day, end_date=day).json()["available"] is available


# AC2-P9 (partition): a blocked venue or a non-operating slot is reported unavailable
def test_availability_whole_venue_status_and_operating_slots(venue):
    client.patch(
        f"/venues/{venue}", json={"status": "blocked", "operating_slots": ["PM"]}
    )
    response = check(venue).json()
    assert response["available"] is False
    assert response["reasons"] == ["venue_unavailable", "outside_operating_slots"]
    assert response["unsupported_slots"] == ["AM"]


# AC2-N3 (negative): an invalid availability request returns 422
@pytest.mark.parametrize(
    "changes",
    [
        {"slots": []},
        {"slots": ["AM", "AM"]},
        {"slots": [None]},
        {"end_date": "2026-09-30"},
        {"slots": ["invalid"]},
        {"created_by": "spoofed"},
    ],
    ids=["AC2-N3a", "AC2-N3b", "AC2-N3c", "AC2-N3d", "AC2-N3e", "AC2-N3f"],
)
def test_invalid_availability_request(venue, changes):
    assert check(venue, **changes).status_code == 422


# AC2-N4 (negative): the availability check for an unknown venue returns 404
def test_missing_venue_availability():
    assert check("missing").status_code == 404
