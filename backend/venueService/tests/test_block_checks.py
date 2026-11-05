import pytest
from fastapi.testclient import TestClient
from time_support import slot_times

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


def make_block(venue, slots=("AM",), **overrides):
    # SCRUM-65: slot names map to their times (AM 07:00-12:00, PM 12:00-18:00).
    response = client.post(
        f"/venues/{venue}/blocks",
        json={
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            **slot_times(slots),
            "reason_category": "maintenance",
        }
        | overrides,
    )
    assert response.status_code == 201
    return response.json()["id"]


def check(venue, slots=("AM",), **overrides):
    return client.post(
        f"/venues/{venue}/availability",
        json={
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            **slot_times(slots),
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
        "conflicts": [
            {
                "block_id": block,
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                # The shared part in time: 07:00-12:00 (SCRUM-65).
                "start_minute": 420,
                "end_minute": 720,
            }
        ],
        "booking_conflicts": [],
        "hold_conflicts": [],
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


# AC2-P9 (partition): a blocked venue is reported unavailable; old operating slots no longer count (SCRUM-65)
def test_availability_whole_venue_status_and_operating_slots(venue):
    client.patch(
        f"/venues/{venue}", json={"status": "blocked", "operating_slots": ["PM"]}
    )
    response = check(venue).json()
    assert response["available"] is False
    assert response["reasons"] == ["venue_unavailable"]


# AC2-N3 (negative): an invalid availability request returns 422
@pytest.mark.parametrize(
    "changes",
    [
        # Times replace slots (SCRUM-65).
        {"start_minute": 425},
        {"start_minute": 720, "end_minute": 720},
        {"start_minute": None},
        {"end_date": "2026-09-30"},
        {"start_minute": "nine"},
        {"created_by": "spoofed"},
    ],
    ids=["AC2-N3a", "AC2-N3b", "AC2-N3c", "AC2-N3d", "AC2-N3e", "AC2-N3f"],
)
def test_invalid_availability_request(venue, changes):
    assert check(venue, **changes).status_code == 422


# AC2-N4 (negative): the availability check for an unknown venue returns 404
def test_missing_venue_availability():
    assert check("missing").status_code == 404
