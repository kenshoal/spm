"""Gap-filling tests for "Search and Filter Venues" (SCRUM-9).

Every test carries its case ID from docs/testcases/scrum_9_testcases.md. The other cases of the
story are in test_venues_search.py and in the availability tests that file names.
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Principal, require_authenticated
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
    }
    payload.update(overrides)
    return client.post("/venues", json=payload).json()


def _sign_in_as(*roles: str) -> None:
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000009", roles=roles
    )


# SCRUM-9 AC3-H1 (happy): each result shows name, location, capacity, layouts, facilities and accessibility
def test_result_shows_the_attributes_a_coordinator_shortlists_by() -> None:
    _make_venue(
        name="Orchard Hall",
        location="Orchard Road",
        max_capacity=180,
        facilities=["projector", "stage"],
        accessibility_features=["ramp"],
        supported_layouts=["theatre", "boardroom"],
    )

    [result] = client.get("/venues/search").json()

    assert result["name"] == "Orchard Hall"
    assert result["location"] == "Orchard Road"
    assert result["max_capacity"] == 180
    assert result["supported_layouts"] == ["theatre", "boardroom"]
    assert result["facilities"] == ["projector", "stage"]
    assert result["accessibility_features"] == ["ramp"]


# SCRUM-9 AC4-B1, AC4-B2, AC4-B3 (boundary): one below, exactly at and one above the maximum capacity
@pytest.mark.parametrize(
    ("required", "shown"),
    [(99, True), (100, True), (101, False)],
    ids=["AC4-B1", "AC4-B2", "AC4-B3"],
)
def test_capacity_boundary_is_the_maximum_capacity(required: int, shown: bool) -> None:
    _make_venue(name="Hundred", max_capacity=100)

    names = [v["name"] for v in client.get("/venues/search", params={"required_capacity": required}).json()]

    assert names == (["Hundred"] if shown else [])


# SCRUM-9 AC4-P1, AC4-P2, AC4-P3 (partition): a chosen layout's own capacity decides (Q&A #112); otherwise the maximum
@pytest.mark.parametrize(
    ("params", "shown"),
    [
        ({"required_capacity": 100, "layout": "classroom"}, False),
        ({"required_capacity": 100, "layout": "theatre"}, True),
        ({"required_capacity": 250}, True),
    ],
    ids=["AC4-P1", "AC4-P2", "AC4-P3"],
)
def test_search_uses_the_chosen_layouts_capacity(params: dict, shown: bool) -> None:
    _make_venue(
        name="Flexible",
        max_capacity=300,
        supported_layouts=["theatre", "classroom"],
        layout_capacities={"classroom": 80},
    )

    names = [v["name"] for v in client.get("/venues/search", params=params).json()]

    assert names == (["Flexible"] if shown else [])


# SCRUM-9 AC4-N1 (negative): a venue below the required capacity is never offered, whatever else matches
def test_a_small_venue_that_matches_every_other_filter_is_still_hidden() -> None:
    _make_venue(
        name="Cosy", max_capacity=40, location="Marina Bay", facilities=["projector"],
        supported_layouts=["theatre"],
    )

    results = client.get(
        "/venues/search",
        params={"required_capacity": 41, "location": "marina", "facility": "projector", "layout": "theatre"},
    ).json()

    assert results == []


# SCRUM-9 AC6-H1, AC6-H2, AC6-H3 (happy): the three permitted roles can search
@pytest.mark.parametrize(
    "role", ["event_coordinator", "venue_staff", "safety_officer"],
    ids=["AC6-H1", "AC6-H2", "AC6-H3"],
)
def test_permitted_roles_can_search(role: str) -> None:
    _make_venue(name="Open")
    _sign_in_as(role)

    response = client.get("/venues/search")

    assert response.status_code == 200
    assert [v["name"] for v in response.json()] == ["Open"]


# SCRUM-9 AC6-N1..N5 (negative): every other role is refused, and nothing is returned
@pytest.mark.parametrize(
    "role",
    ["event_organiser", "attendee", "technical_support", "event_operations_manager", "admin"],
    ids=["AC6-N1", "AC6-N2", "AC6-N3", "AC6-N4", "AC6-N5"],
)
def test_other_roles_are_refused_a_search(role: str) -> None:
    _make_venue(name="Internal")
    _sign_in_as(role)

    response = client.get("/venues/search")

    assert response.status_code == 403
    assert "Internal" not in response.text


# SCRUM-9 AC6-P1 (partition): a person with several roles may search when any one is permitted
def test_a_multi_role_user_may_search_if_one_role_is_permitted() -> None:
    _make_venue(name="Open")
    _sign_in_as("attendee", "event_coordinator")

    assert client.get("/venues/search").status_code == 200


# SCRUM-9 AC6-N6 (negative): a search with no session is refused with 401
def test_a_search_without_a_session_is_unauthenticated() -> None:
    app.dependency_overrides.clear()

    assert client.get("/venues/search").status_code == 401
