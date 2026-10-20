"""Tests for the "Search and Filter Venues" card."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_venue(**overrides: object) -> dict:
    payload = {
        "name": "Venue",
        "location": "Somewhere",
        "max_capacity": 100,
        "facilities": [],
        "accessibility_features": [],
        "supported_layouts": [],
        "operating_slots": ["AM", "PM", "NIGHT"],
    }
    payload.update(overrides)
    return client.post("/venues", json=payload).json()


def test_capacity_filter_excludes_venues_below_requested_attendance() -> None:
    _make_venue(name="Small", max_capacity=50)
    _make_venue(name="Big", max_capacity=300)

    response = client.get("/venues/search", params={"required_capacity": 100})

    assert response.status_code == 200
    assert [v["name"] for v in response.json()] == ["Big"]


def test_blocked_venue_is_excluded() -> None:
    ok = _make_venue(name="Open")
    blocked = _make_venue(name="Closed")
    client.patch(f"/venues/{blocked['id']}", json={"status": "blocked"})

    response = client.get("/venues/search")

    assert [v["name"] for v in response.json()] == [ok["name"]]


def test_location_filter_is_case_insensitive_substring() -> None:
    _make_venue(name="Central", location="Marina Bay")
    _make_venue(name="East", location="Tampines")

    response = client.get("/venues/search", params={"location": "marina"})

    assert [v["name"] for v in response.json()] == ["Central"]


def test_layout_filter_matches_supported_layout() -> None:
    _make_venue(name="Theatre-ready", supported_layouts=["theatre", "classroom"])
    _make_venue(name="Boardroom-only", supported_layouts=["boardroom"])

    response = client.get("/venues/search", params={"layout": "theatre"})

    assert [v["name"] for v in response.json()] == ["Theatre-ready"]


# SCRUM-65 AC4-P2 (partition): per-venue operating slots no longer filter search;
# every venue operates 07:00-24:00 (Product Owner, 20 October 2026)
def test_slot_filter_matches_operating_slots() -> None:
    _make_venue(name="Evenings", operating_slots=["NIGHT"])
    _make_venue(name="Mornings", operating_slots=["AM"])

    response = client.get(
        "/venues/search",
        params={"date": "2030-01-10", "start_minute": 1080, "end_minute": 1200},
    )

    assert sorted(v["name"] for v in response.json()) == ["Evenings", "Mornings"]


def test_facility_filter_requires_all_requested_facilities() -> None:
    _make_venue(name="Full", facilities=["projector", "microphone", "stage"])
    _make_venue(name="Partial", facilities=["projector"])

    response = client.get(
        "/venues/search", params=[("facility", "projector"), ("facility", "microphone")]
    )

    assert [v["name"] for v in response.json()] == ["Full"]


def test_accessibility_filter_requires_all_requested_features() -> None:
    _make_venue(name="Accessible", accessibility_features=["ramp", "hearing_loop"])
    _make_venue(name="Some", accessibility_features=["ramp"])

    response = client.get(
        "/venues/search",
        params=[("accessibility", "ramp"), ("accessibility", "hearing_loop")],
    )

    assert [v["name"] for v in response.json()] == ["Accessible"]


def test_all_filters_apply_together() -> None:
    _make_venue(
        name="Match",
        location="Marina Bay",
        max_capacity=250,
        facilities=["projector"],
        supported_layouts=["theatre"],
        operating_slots=["PM"],
    )
    _make_venue(
        name="WrongCapacity",
        location="Marina Bay",
        max_capacity=100,
        facilities=["projector"],
        supported_layouts=["theatre"],
        operating_slots=["PM"],
    )
    _make_venue(
        name="WrongLayout",
        location="Marina Bay",
        max_capacity=250,
        facilities=["projector"],
        supported_layouts=["boardroom"],
        operating_slots=["PM"],
    )

    response = client.get(
        "/venues/search",
        params={
            "location": "marina",
            "required_capacity": 200,
            "facility": "projector",
            "layout": "theatre",
            # A PM time since SCRUM-65; all three venues are free then.
            "date": "2030-01-10",
            "start_minute": 720,
            "end_minute": 1080,
        },
    )

    assert [v["name"] for v in response.json()] == ["Match"]


def test_no_filters_returns_all_available_venues() -> None:
    _make_venue(name="One")
    _make_venue(name="Two")

    response = client.get("/venues/search")

    assert {v["name"] for v in response.json()} == {"One", "Two"}


def test_date_search_returns_venue_without_blocks() -> None:
    _make_venue(name="Any")

    response = client.get("/venues/search", params={"date": "2026-10-01"})

    assert response.status_code == 200
    assert [v["name"] for v in response.json()] == ["Any"]
