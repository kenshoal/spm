"""Gap-filling tests for "Maintain the Venue Catalogue" (SCRUM-30).

Every test carries its case ID from docs/testcases/scrum_30_testcases.md. The basic create, read,
update and list cases are in test_venues_catalogue.py.
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)

FULL = {
    "name": "Orchard Hall",
    "location": "Orchard Road",
    "max_capacity": 200,
    "facilities": ["projector", "microphone"],
    "accessibility_features": ["wheelchair_ramp", "hearing_loop"],
    "supported_layouts": ["theatre", "classroom"],
    "operating_slots": ["AM", "PM"],
}


def _create(**overrides: object) -> dict:
    return client.post("/venues", json={**FULL, **overrides}).json()


def _sign_in_as(*roles: str) -> None:
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000009", roles=roles
    )
    app.dependency_overrides.pop(require_venue_staff, None)


# SCRUM-30 AC1-H6 (happy): Venue Staff create a venue with every catalogue attribute and all are stored
def test_create_stores_every_attribute() -> None:
    response = client.post("/venues", json=FULL)

    assert response.status_code == 201
    body = response.json()
    for field, value in FULL.items():
        assert body[field] == value, field
    assert client.get(f"/venues/{body['id']}").json()[field] == value


# SCRUM-30 AC1-H7 (happy): Venue Staff update every attribute at once
def test_update_changes_every_attribute() -> None:
    venue = _create()
    changes = {
        "name": "Orchard Grand Hall",
        "location": "Marina Bay",
        "max_capacity": 450,
        "facilities": ["stage"],
        "accessibility_features": ["lift"],
        "supported_layouts": ["banquet"],
        "operating_slots": ["NIGHT"],
    }

    response = client.patch(f"/venues/{venue['id']}", json=changes)

    assert response.status_code == 200
    for field, value in changes.items():
        assert response.json()[field] == value, field


# SCRUM-30 AC1-P6 (partition): a venue may be created with no facilities, accessibility or layouts
def test_optional_lists_may_be_empty() -> None:
    response = client.post(
        "/venues",
        json={"name": "Bare", "location": "Anywhere", "max_capacity": 10},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["facilities"] == []
    assert body["accessibility_features"] == []
    assert body["supported_layouts"] == []


# SCRUM-30 AC1-B1, AC1-B2 (boundary): a maximum capacity of 1 is accepted and 0 is refused
@pytest.mark.parametrize(("capacity", "status"), [(1, 201), (0, 422)], ids=["AC1-B1", "AC1-B2"])
def test_capacity_boundary(capacity: int, status: int) -> None:
    response = client.post("/venues", json={**FULL, "max_capacity": capacity})

    assert response.status_code == status
    assert len(client.get("/venues").json()) == (1 if status == 201 else 0)


# SCRUM-30 AC1-N8, AC1-N9, AC1-N10, AC1-N11 (negative): invalid input is refused and nothing is stored
@pytest.mark.parametrize(
    "bad",
    [
        {"max_capacity": -5},
        {"max_capacity": "many"},
        {"location": ""},
        {"supported_layouts": ["spaceship"]},
    ],
    ids=["AC1-N8", "AC1-N9", "AC1-N10", "AC1-N11"],
)
def test_invalid_venue_is_refused(bad: dict) -> None:
    response = client.post("/venues", json={**FULL, **bad})

    assert response.status_code == 422
    assert client.get("/venues").json() == []


# SCRUM-30 AC1-N12 (negative): a refused update changes nothing
def test_invalid_update_leaves_the_venue_unchanged() -> None:
    venue = _create()

    response = client.patch(f"/venues/{venue['id']}", json={"max_capacity": 0})

    assert response.status_code == 422
    assert client.get(f"/venues/{venue['id']}").json() == venue


# SCRUM-30 AC1-X1..X5 (cross-cutting): only Venue Staff create or update; every other role gets 403
@pytest.mark.parametrize(
    "role",
    ["event_coordinator", "safety_officer", "event_organiser", "technical_support", "attendee"],
    ids=["AC1-X1", "AC1-X2", "AC1-X3", "AC1-X4", "AC1-X5"],
)
def test_other_roles_cannot_change_the_catalogue(role: str) -> None:
    venue = _create()
    _sign_in_as(role)

    created = client.post("/venues", json=FULL)
    updated = client.patch(f"/venues/{venue['id']}", json={"max_capacity": 1})

    assert (created.status_code, updated.status_code) == (403, 403)
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000001", roles=("venue_staff",)
    )
    assert client.get(f"/venues/{venue['id']}").json() == venue


# SCRUM-30 AC2-H3, AC2-H4, AC2-H5 (happy): the three permitted roles read the current attributes
@pytest.mark.parametrize(
    "role", ["event_coordinator", "venue_staff", "safety_officer"],
    ids=["AC2-H3", "AC2-H4", "AC2-H5"],
)
def test_permitted_roles_read_current_attributes(role: str) -> None:
    venue = _create()
    client.patch(f"/venues/{venue['id']}", json={"max_capacity": 260})
    _sign_in_as(role)

    response = client.get(f"/venues/{venue['id']}")

    assert response.status_code == 200
    assert response.json()["max_capacity"] == 260
    assert response.json()["facilities"] == ["projector", "microphone"]


# SCRUM-30 AC2-N4, AC2-N5, AC2-N6 (negative): roles outside the permitted three cannot read a venue
@pytest.mark.parametrize(
    "role", ["event_organiser", "technical_support", "event_operations_manager"],
    ids=["AC2-N4", "AC2-N5", "AC2-N6"],
)
def test_other_roles_cannot_read_a_venue(role: str) -> None:
    venue = _create()
    _sign_in_as(role)

    assert client.get(f"/venues/{venue['id']}").status_code == 403
    assert client.get("/venues").status_code == 403


# SCRUM-30 AC3-X1 (cross-cutting): an updated capacity changes who is found by search
def test_updated_capacity_is_reflected_in_search() -> None:
    venue = _create(max_capacity=50)
    assert client.get("/venues/search", params={"required_capacity": 120}).json() == []

    client.patch(f"/venues/{venue['id']}", json={"max_capacity": 150})

    assert [v["name"] for v in client.get("/venues/search", params={"required_capacity": 120}).json()] == [
        "Orchard Hall"
    ]


# SCRUM-30 AC3-X2 (cross-cutting): updated facilities, accessibility and layouts change what search finds
def test_updated_lists_are_reflected_in_search() -> None:
    venue = _create(facilities=[], accessibility_features=[], supported_layouts=["theatre"])
    wanted = [("facility", "stage"), ("accessibility", "lift"), ("layout", "banquet")]
    assert client.get("/venues/search", params=wanted).json() == []

    client.patch(
        f"/venues/{venue['id']}",
        json={"facilities": ["stage"], "accessibility_features": ["lift"], "supported_layouts": ["banquet"]},
    )

    assert [v["name"] for v in client.get("/venues/search", params=wanted).json()] == ["Orchard Hall"]


# SCRUM-30 AC3-X3 (cross-cutting): taking a venue out of service removes it from search
def test_blocking_a_venue_removes_it_from_search() -> None:
    venue = _create()
    assert len(client.get("/venues/search").json()) == 1

    client.patch(f"/venues/{venue['id']}", json={"status": "blocked"})

    assert client.get("/venues/search").json() == []


# SCRUM-30 AC3-X4 (cross-cutting): an updated capacity and facilities change a suitability verdict
def test_updates_are_reflected_in_suitability() -> None:
    venue = _create(max_capacity=40, facilities=[])
    ask = {"expected_attendance": 80, "required_facilities": ["stage"]}
    before = client.post(f"/venues/{venue['id']}/suitability", json=ask).json()
    assert before["suitable"] is False
    assert sorted(m["attribute"] for m in before["mismatches"]) == ["capacity", "facilities"]

    client.patch(f"/venues/{venue['id']}", json={"max_capacity": 90, "facilities": ["stage"]})

    after = client.post(f"/venues/{venue['id']}/suitability", json=ask).json()
    assert after["suitable"] is True
    assert after["mismatches"] == []
