"""Tests for the "Maintain the Venue Catalogue" card."""

from fastapi.testclient import TestClient

from app.dependencies import Principal, require_authenticated, require_venue_staff
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


# SCRUM-30 AC1-H1 (happy): creating a venue stores it and returns the record
def test_create_venue_returns_stored_record() -> None:
    response = client.post("/venues", json=_sample_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == "Orchard Hall"
    assert body["status"] == "available"
    assert body["created_at"]
    assert body["updated_at"]


# SCRUM-30 AC1-N1 (negative): a non-Venue-Staff role is refused venue creation with 403
def test_non_venue_staff_cannot_create_venue() -> None:
    def forbidden() -> Principal:
        return Principal(
            user_id="00000000-0000-0000-0000-000000000001",
            roles=("event_operations_manager",),
        )

    app.dependency_overrides[require_authenticated] = forbidden
    app.dependency_overrides.pop(require_venue_staff, None)
    try:
        response = client.post("/venues", json=_sample_payload())
    finally:
        app.dependency_overrides[require_venue_staff] = lambda: Principal(
            user_id="00000000-0000-0000-0000-000000000001",
            roles=("venue_staff",),
        )

    assert response.status_code == 403


# SCRUM-30 AC2-N2 (negative): reading the catalogue without a session is refused with 401
def test_venue_routes_require_authentication() -> None:
    app.dependency_overrides.clear()

    response = client.get("/venues")

    assert response.status_code == 401


# SCRUM-30 AC1-N2 (negative): a non-positive capacity is refused at creation with 422
def test_create_venue_rejects_non_positive_capacity() -> None:
    response = client.post("/venues", json=_sample_payload(max_capacity=0))

    assert response.status_code == 422


# SCRUM-30 AC2-H1 (happy): viewing a venue shows its stored attributes
def test_get_venue_shows_current_attributes() -> None:
    created = client.post("/venues", json=_sample_payload()).json()

    response = client.get(f"/venues/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


# SCRUM-30 AC2-N1 (negative): an unknown venue id returns 404
def test_get_missing_venue_returns_404() -> None:
    response = client.get("/venues/does-not-exist")

    assert response.status_code == 404


# SCRUM-30 AC1-H2 (happy): a partial update changes only the sent fields
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


# SCRUM-30 AC1-P1 (partition): the status can be updated to blocked
def test_update_venue_can_block_it() -> None:
    created = client.post("/venues", json=_sample_payload()).json()

    response = client.patch(f"/venues/{created['id']}", json={"status": "blocked"})

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


# SCRUM-30 AC1-N3 (negative): updating an unknown venue returns 404
def test_update_missing_venue_returns_404() -> None:
    response = client.patch("/venues/does-not-exist", json={"max_capacity": 10})

    assert response.status_code == 404


# SCRUM-30 AC2-P1 (partition): the catalogue lists every venue
def test_list_venues_returns_all_created() -> None:
    client.post("/venues", json=_sample_payload(name="A"))
    client.post("/venues", json=_sample_payload(name="B"))

    response = client.get("/venues")

    assert response.status_code == 200
    assert {v["name"] for v in response.json()} == {"A", "B"}


# SCRUM-30 AC2-N3 (negative): an attendee is refused catalogue reads with 403
def test_venue_reads_forbidden_for_attendees() -> None:
    venue_id = client.post("/venues", json=_sample_payload()).json()["id"]
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000002",
        roles=("attendee",),
    )

    responses = [
        client.get("/venues"),
        client.get("/venues/search"),
        client.get(f"/venues/{venue_id}"),
        client.post(
            f"/venues/{venue_id}/suitability",
            json={"expected_attendance": 10},
        ),
    ]

    assert all(response.status_code == 403 for response in responses)
