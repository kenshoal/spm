"""Router tests for the "Check Venue Suitability" story (SCRUM-12).

Every test carries its case ID from docs/testcases/scrum_12_testcases.md.
"""

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Principal, require_authenticated
from app.main import app

client = TestClient(app)


def _make_venue(**overrides: object) -> dict:
    payload = {
        "name": "Orchard Hall",
        "location": "Orchard Road",
        "max_capacity": 100,
        "facilities": ["Projector"],
        "accessibility_features": [],
        "supported_layouts": ["theatre"],
        "operating_slots": ["AM", "PM"],
    }
    payload.update(overrides)
    return client.post("/venues", json=payload).json()


# AC4-H1 (happy): a suitable venue returns suitable true and no mismatches
def test_suitable_venue_returns_no_mismatches() -> None:
    venue = _make_venue()

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 100, "required_facilities": ["Projector"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["venue_id"] == venue["id"]
    assert body["suitable"] is True
    assert body["mismatches"] == []


# AC4-H2 (happy): an unsuitable venue returns one reasoned mismatch per failed attribute
def test_unsuitable_venue_returns_a_reason_per_mismatch() -> None:
    venue = _make_venue(max_capacity=20)

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 50, "required_facilities": ["Stage"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suitable"] is False
    attributes = [mismatch["attribute"] for mismatch in body["mismatches"]]
    assert sorted(attributes) == ["capacity", "facilities"]
    assert all(mismatch["reason"] for mismatch in body["mismatches"])


# AC1-N1, AC1-N2 (negative): a non-positive attendance is rejected and nothing changes
@pytest.mark.parametrize("attendance", [0, -1], ids=["AC1-N1", "AC1-N2"])
def test_non_positive_attendance_is_rejected(attendance: int) -> None:
    venue = _make_venue()
    before = client.get(f"/venues/{venue['id']}").json()

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": attendance},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "greater_than"
    assert response.json()["detail"][0]["loc"] == ["body", "expected_attendance"]
    assert client.get(f"/venues/{venue['id']}").json() == before


# AC3-N1 (negative): an unknown venue returns 404 Venue not found
def test_unknown_venue_returns_404() -> None:
    response = client.post(
        "/venues/does-not-exist/suitability",
        json={"expected_attendance": 10},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue not found"


# AC3-N2 (negative): an unknown layout value is rejected and the venue is unchanged
def test_unknown_layout_value_is_rejected() -> None:
    venue = _make_venue()
    before = client.get(f"/venues/{venue['id']}").json()

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 10, "required_layout": "ballroom"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "required_layout"]
    assert response.json()["detail"][0]["type"] == "enum"
    assert client.get(f"/venues/{venue['id']}").json() == before


# AC3-N3 (negative): an off-step time (times replace slots, SCRUM-65) is rejected and the venue is unchanged
def test_unknown_slot_value_is_rejected() -> None:
    venue = _make_venue()
    before = client.get(f"/venues/{venue['id']}").json()

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 10, "required_start_minute": 610,
              "required_end_minute": 720},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "off_step"
    assert client.get(f"/venues/{venue['id']}").json() == before


# AC3-X2 (cross-cutting): a request without a bearer token is refused with 401
def test_check_requires_authentication() -> None:
    venue = _make_venue()
    app.dependency_overrides.clear()

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 10},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


# AC3-X3 (cross-cutting): an Event Coordinator, who is not venue staff, may run the check
def test_event_coordinator_can_run_the_check() -> None:
    venue = _make_venue()
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000002",
        roles=("event_coordinator",),
    )

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 10},
    )

    assert response.status_code == 200
    assert response.json()["suitable"] is True


# AC5-X1 (cross-cutting): a check, suitable or not, leaves the venue and the catalogue unchanged
def test_check_never_changes_the_venue_or_the_catalogue() -> None:
    venue = _make_venue(max_capacity=20)
    venue_before = client.get(f"/venues/{venue['id']}").json()
    catalogue_before = client.get("/venues").json()

    suitable = client.post(
        f"/venues/{venue['id']}/suitability", json={"expected_attendance": 20}
    )
    unsuitable = client.post(
        f"/venues/{venue['id']}/suitability", json={"expected_attendance": 500}
    )

    assert suitable.json()["suitable"] is True
    assert unsuitable.json()["suitable"] is False
    assert client.get(f"/venues/{venue['id']}").json() == venue_before
    assert client.get("/venues").json() == catalogue_before
