"""Tests for the "Maintain the Venue Catalogue" card."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _sample_payload(**overrides: object) -> dict:
    payload = {
        "name": "Orchard Hall",
        "location": "Orchard Road",
        "max_capacity": 200,
        "facilities": ["projector", "microphone"],
        "accessibility_features": ["wheelchair_ramp"],
        "supported_layouts": ["theatre", "classroom"],
        "operating_slots": ["AM", "PM", "NIGHT"],
    }
    payload.update(overrides)
    return payload


def test_create_venue_returns_stored_record() -> None:
    response = client.post("/venues", json=_sample_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == "Orchard Hall"
    assert body["status"] == "available"
    assert body["created_at"]
    assert body["updated_at"]


def test_create_venue_rejects_non_positive_capacity() -> None:
    response = client.post("/venues", json=_sample_payload(max_capacity=0))

    assert response.status_code == 422


def test_get_venue_shows_current_attributes() -> None:
    created = client.post("/venues", json=_sample_payload()).json()

    response = client.get(f"/venues/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_missing_venue_returns_404() -> None:
    response = client.get("/venues/does-not-exist")

    assert response.status_code == 404


def test_update_venue_applies_partial_changes() -> None:
    created = client.post("/venues", json=_sample_payload()).json()

    response = client.patch(
        f"/venues/{created['id']}",
        json={"max_capacity": 350, "facilities": ["projector", "stage"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["max_capacity"] == 350
    assert body["facilities"] == ["projector", "stage"]
    assert body["name"] == "Orchard Hall"  # untouched
    assert body["updated_at"] >= created["updated_at"]


def test_update_venue_can_block_it() -> None:
    created = client.post("/venues", json=_sample_payload()).json()

    response = client.patch(f"/venues/{created['id']}", json={"status": "blocked"})

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


def test_update_missing_venue_returns_404() -> None:
    response = client.patch("/venues/does-not-exist", json={"max_capacity": 10})

    assert response.status_code == 404


def test_list_venues_returns_all_created() -> None:
    client.post("/venues", json=_sample_payload(name="A"))
    client.post("/venues", json=_sample_payload(name="B"))

    response = client.get("/venues")

    assert response.status_code == 200
    assert {v["name"] for v in response.json()} == {"A", "B"}
