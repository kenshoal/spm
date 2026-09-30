"""Router tests for the "Check Venue Suitability" card."""

from fastapi.testclient import TestClient

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


def test_unsuitable_venue_returns_reasons() -> None:
    venue = _make_venue(max_capacity=20)

    response = client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 50, "required_facilities": ["Stage"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suitable"] is False
    attributes = {m["attribute"] for m in body["mismatches"]}
    assert attributes == {"capacity", "facilities"}


def test_unknown_venue_returns_404() -> None:
    response = client.post(
        "/venues/does-not-exist/suitability",
        json={"expected_attendance": 10},
    )

    assert response.status_code == 404


def test_check_never_mutates_the_venue() -> None:
    venue = _make_venue(max_capacity=20)

    client.post(
        f"/venues/{venue['id']}/suitability",
        json={"expected_attendance": 500},
    )

    unchanged = client.get(f"/venues/{venue['id']}").json()
    assert unchanged["max_capacity"] == 20
    assert unchanged["status"] == "available"
