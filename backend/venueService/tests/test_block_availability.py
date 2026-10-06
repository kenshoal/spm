"""Create, retrieve and search using stored venue blocks."""

import pytest
from fastapi.testclient import TestClient

from app.block_models import BlockStatus
from app.block_repository import block_repository
from app.main import app

client = TestClient(app)


def make_venue(**overrides):
    response = client.post(
        "/venues",
        json={"name": "Hall", "location": "Campus", "max_capacity": 100} | overrides,
    )
    assert response.status_code == 201
    return response.json()["id"]


def make_block(venue_id, **overrides):
    response = client.post(
        f"/venues/{venue_id}/blocks",
        json={
            "start_date": "2026-09-20",
            "end_date": "2026-09-22",
            "slots": ["AM"],
            "reason_category": "maintenance",
        }
        | overrides,
    )
    assert response.status_code == 201
    return response.json()


def search(**params):
    response = client.get("/venues/search", params=params)
    assert response.status_code == 200
    return {venue["id"] for venue in response.json()}


# AC4-H2 (happy): a venue's block list is scoped to it and keeps lifted blocks
def test_list_blocks_is_scoped_and_includes_lifted_records():
    venue_id, other_id = make_venue(), make_venue()
    active = make_block(venue_id)
    lifted = make_block(venue_id, slots=["PM"])
    # There is no lifting endpoint yet; seed the stored state directly for this test.
    block_repository.get(lifted["id"]).status = BlockStatus.LIFTED
    lifted["status"] = "lifted"
    make_block(other_id)

    response = client.get(f"/venues/{venue_id}/blocks")
    assert response.status_code == 200
    assert response.json() == [active, lifted]


# AC4-P7 (partition): a venue with no blocks returns an empty list
def test_list_blocks_for_venue_without_blocks():
    venue_id = make_venue()
    response = client.get(f"/venues/{venue_id}/blocks")
    assert response.status_code == 200
    assert response.json() == []


# AC4-N4 (negative): listing blocks for an unknown venue returns 404
def test_list_blocks_for_missing_venue():
    response = client.get("/venues/missing/blocks")
    assert response.status_code == 404
    assert response.json()["detail"] == "Venue not found"


# AC2-H1 (happy): search excludes a venue on both boundary dates of its block
@pytest.mark.parametrize("on_date", ["2026-09-20", "2026-09-21", "2026-09-22"], ids=["AC2-H1a", "AC2-H1b", "AC2-H1c"])
def test_creation_to_listing_to_search_includes_both_boundary_dates(on_date):
    venue_id, other_id = make_venue(), make_venue()
    assert venue_id in search(date=on_date, slot="AM")
    block = make_block(venue_id)
    assert client.get(f"/venues/{venue_id}/blocks").json() == [block]
    assert search(date=on_date, slot="AM") == {other_id}
    assert client.get(f"/venues/{venue_id}").json()["status"] == "available"


# AC2-P1 (partition): other dates and slots still offer the venue
@pytest.mark.parametrize(
    "on_date,slot",
    [
        ("2026-09-19", "AM"),
        ("2026-09-23", "AM"),
        ("2026-09-21", "PM"),
        ("2026-09-21", "NIGHT"),
    ],
    ids=["AC2-P1a", "AC2-P1b", "AC2-P1c", "AC2-P1d"],
)
def test_non_overlapping_search_keeps_venue(on_date, slot):
    venue_id = make_venue()
    make_block(venue_id)
    assert search(date=on_date, slot=slot) == {venue_id}


# AC2-P3 (partition): a lifted block does not hide the venue
def test_lifted_block_does_not_restrict_search():
    venue_id = make_venue()
    block = make_block(venue_id)
    block_repository.get(block["id"]).status = BlockStatus.LIFTED
    assert search(date="2026-09-21", slot="AM") == {venue_id}
    assert search(date="2026-09-21") == {venue_id}


# AC2-P4 (partition): a search without a date makes no dated availability claim
def test_search_without_date_does_not_apply_dated_blocks():
    venue_id = make_venue()
    make_block(venue_id, slots=["AM", "PM", "NIGHT"])
    assert search() == {venue_id}
    assert search(slot="AM") == {venue_id}


# AC2-P5 (partition): a date-only search needs one operating slot free across all blocks
def test_date_only_search_requires_one_free_operating_slot_across_all_blocks():
    venue_id = make_venue(operating_slots=["AM", "PM"])
    make_block(venue_id, slots=["AM"])
    assert search(date="2026-09-21") == {venue_id}
    make_block(venue_id, slots=["PM"])
    assert search(date="2026-09-21") == set()
    assert search(date="2026-09-23") == {venue_id}


# AC2-B4 (boundary): a block on every slot excludes a date-only search
def test_full_day_block_excludes_date_only_search():
    venue_id = make_venue()
    make_block(venue_id, slots=["AM", "PM", "NIGHT"])
    assert search(date="2026-09-21") == set()


# AC2-P6 (partition): a block on a non-operating slot does not hide the venue
def test_date_only_search_ignores_blocks_outside_operating_slots():
    venue_id = make_venue(operating_slots=["AM"])
    make_block(venue_id, slots=["PM"])
    assert search(date="2026-09-21") == {venue_id}
    assert search(date="2026-09-21", slot="PM") == set()


# AC2-P7 (partition): a venue with no operating slots is not offered for a date
def test_date_only_search_excludes_venue_without_operating_slots():
    make_venue(operating_slots=[])
    assert search(date="2026-09-21") == set()


# AC2-B5 (boundary): a NIGHT block affects its starting date only
def test_night_block_belongs_to_starting_date():
    venue_id = make_venue()
    make_block(venue_id, end_date="2026-09-20", slots=["NIGHT"])
    assert search(date="2026-09-20", slot="NIGHT") == set()
    assert search(date="2026-09-21", slot="NIGHT") == {venue_id}


# AC2-P8 (partition): dated search still applies every catalogue filter
def test_dated_search_preserves_catalogue_filters():
    attributes = {
        "location": "Marina Bay",
        "max_capacity": 200,
        "facilities": ["projector"],
        "accessibility_features": ["ramp"],
        "supported_layouts": ["theatre"],
        "operating_slots": ["PM"],
    }
    match = make_venue(**attributes)
    blocked = make_venue(**attributes)
    make_block(blocked, slots=["PM"])
    for mismatch in [
        {"location": "East"},
        {"max_capacity": 50},
        {"facilities": []},
        {"accessibility_features": []},
        {"supported_layouts": []},
        {"operating_slots": ["AM"]},
    ]:
        make_venue(**(attributes | mismatch))
    closed = make_venue(**attributes)
    client.patch(f"/venues/{closed}", json={"status": "blocked"})
    assert search(
        date="2026-09-21",
        slot="PM",
        location="marina",
        required_capacity=100,
        facility="projector",
        accessibility="ramp",
        layout="theatre",
    ) == {match}


# AC2-N2 (negative): an invalid date or slot in search returns 422
@pytest.mark.parametrize("params", [{"date": "invalid"}, {"slot": "invalid"}], ids=["AC2-N2a", "AC2-N2b"])
def test_invalid_search_parameters(params):
    assert client.get("/venues/search", params=params).status_code == 422
