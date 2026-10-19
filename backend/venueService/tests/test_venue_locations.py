"""SCRUM-13 D11: the venue-locations contract (AC1-X3, AC1-X4, AC1-X5).

Technical Support needs each venue's id, name and building to work out
equipment transfer days, and nothing else in the catalogue.
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)


def _payload(**overrides: object) -> dict:
    payload = {
        "name": "Orchard Hall",
        "location": "Orchard Road",
        "max_capacity": 200,
        "facilities": ["projector"],
        "accessibility_features": [],
        "supported_layouts": ["theatre"],
        "operating_slots": ["AM", "PM"],
    }
    payload.update(overrides)
    return payload


def _as(*roles: str) -> None:
    """Act as a user holding exactly these roles, with the real role checks."""

    app.dependency_overrides.pop(require_venue_staff, None)
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000013", roles=tuple(roles)
    )


@pytest.fixture
def venue_ids() -> dict[str, str]:
    """Two buildings and one blocked venue, as SCRUM-10's VENUES (seeded as staff)."""

    ids = {}
    for name, location in [
        ("Search Big Hall", "Search Wing"),
        ("Harbour Room", "Harbour Block"),
        ("Search Closed Hall", "Search Wing"),
    ]:
        response = client.post("/venues", json=_payload(name=name, location=location))
        assert response.status_code == 201
        ids[name] = response.json()["id"]
    blocked = client.patch(
        f"/venues/{ids['Search Closed Hall']}", json={"status": "blocked"}
    )
    assert blocked.status_code == 200
    return ids


# AC1-X3 (cross-cutting): Technical Support reads id, name and location of every venue
def test_staff_read_venue_locations(venue_ids: dict[str, str]) -> None:
    _as("technical_support")

    response = client.get("/venues/locations")

    assert response.status_code == 200
    body = response.json()
    assert sorted(body, key=lambda v: v["name"]) == sorted(
        [
            {
                "id": venue_ids["Search Big Hall"],
                "name": "Search Big Hall",
                "location": "Search Wing",
            },
            {
                "id": venue_ids["Harbour Room"],
                "name": "Harbour Room",
                "location": "Harbour Block",
            },
            {
                "id": venue_ids["Search Closed Hall"],
                "name": "Search Closed Hall",
                "location": "Search Wing",
            },
        ],
        key=lambda v: v["name"],
    )
    assert all(set(item) == {"id", "name", "location"} for item in body)


# AC1-X3 (cross-cutting): the response is not the full catalogue
def test_locations_are_not_the_full_catalogue(venue_ids: dict[str, str]) -> None:
    _as("technical_support")

    body = client.get("/venues/locations").json()

    assert len(body) == len(venue_ids)
    for item in body:
        for field in ("max_capacity", "facilities", "status", "created_at"):
            assert field not in item


# AC1-X5 (cross-cutting): existing venue readers can read locations too
@pytest.mark.parametrize(
    "roles",
    [
        ("event_coordinator",),
        ("venue_staff",),
        ("event_operations_manager", "technical_support"),
    ],
)
def test_existing_readers_can_read_locations(
    venue_ids: dict[str, str], roles: tuple[str, ...]
) -> None:
    _as(*roles)

    response = client.get("/venues/locations")

    assert response.status_code == 200
    assert len(response.json()) == len(venue_ids)


# AC1-X5 (cross-cutting): other roles may not read locations
@pytest.mark.parametrize(
    "role", ["attendee", "event_organiser", "event_operations_manager"]
)
def test_other_roles_cannot_read_locations(role: str) -> None:
    _as(role)

    response = client.get("/venues/locations")

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


# AC1-X5 (cross-cutting): reading locations requires a session
def test_locations_require_a_session() -> None:
    app.dependency_overrides.pop(require_authenticated, None)

    response = client.get("/venues/locations")

    assert response.status_code == 401


# AC1-X4 (cross-cutting): Technical Support still cannot read the catalogue
def test_staff_still_cannot_read_the_catalogue(venue_ids: dict[str, str]) -> None:
    venue = venue_ids["Search Big Hall"]
    _as("technical_support")

    responses = {
        "GET /venues": client.get("/venues"),
        "GET /venues/search": client.get("/venues/search"),
        "GET /venues/{id}": client.get(f"/venues/{venue}"),
        "GET /venues/{id}/blocks": client.get(f"/venues/{venue}/blocks"),
        "POST /venues/{id}/suitability": client.post(
            f"/venues/{venue}/suitability", json={"expected_attendance": 10}
        ),
        "GET /booking-requests": client.get("/booking-requests"),
    }

    assert {route: r.status_code for route, r in responses.items()} == {
        route: 403 for route in responses
    }


# AC1-X3 (cross-cutting): "locations" is a route, not a venue id
def test_locations_route_is_not_a_venue_id(venue_ids: dict[str, str]) -> None:
    _as("venue_staff")

    response = client.get("/venues/locations")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
