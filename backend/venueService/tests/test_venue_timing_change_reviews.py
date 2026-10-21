"""SCRUM-20 AC6: venue setup/turnaround changes go through update_venue_timing.

Case IDs match docs/testcases/scrum_20_testcases.md. The flags, change record and
rollback are verified in the database (verify_venue_timing_change_reviews.sql);
these tests cover the API routing and the Supabase call.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Venue, VenueCreate, VenueUpdate
from app.repository import get_repository, repository
from app.supabase_repository import SupabaseRepositoryError, SupabaseVenueRepository

client = TestClient(app)
STAFF_ID = "00000000-0000-0000-0000-000000000001"
VENUE_ID = "2a192261-5e90-4398-90ff-1a2d0eaaff00"


def make_venue(**overrides: object) -> dict:
    body = {"name": "Orchard Hall", "location": "Orchard", "max_capacity": 100} | overrides
    response = client.post("/venues", json=body)
    assert response.status_code == 201
    return response.json()


class RecordingStore:
    """Wraps the memory store and records which method each change used."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def create(self, data: VenueCreate) -> Venue:
        return repository.create(data)

    def get(self, venue_id: str) -> Venue | None:
        return repository.get(venue_id)

    def update(self, venue_id: str, data: VenueUpdate) -> Venue | None:
        self.calls.append(("update", venue_id, data.model_dump(exclude_unset=True)))
        return repository.update(venue_id, data)

    def update_timing(self, venue_id, setup_minutes, turnaround_minutes, changed_by):
        self.calls.append(("update_timing", venue_id, setup_minutes, turnaround_minutes, changed_by))
        return repository.update_timing(venue_id, setup_minutes, turnaround_minutes, changed_by)


@pytest.fixture
def store() -> RecordingStore:
    recording = RecordingStore()
    app.dependency_overrides[get_repository] = lambda: recording
    return recording


# AC6-API1 (happy): a time change goes through update_timing as the signed-in Venue Staff,
# and the other fields in the same request are a plain update
def test_time_change_goes_through_update_timing_with_the_actor(store: RecordingStore) -> None:
    venue_id = make_venue(setup_minutes=0, turnaround_minutes=0)["id"]

    response = client.patch(
        f"/venues/{venue_id}", json={"turnaround_minutes": 45, "name": "Orchard Hall B"}
    )

    assert response.status_code == 200
    assert store.calls == [
        ("update_timing", venue_id, None, 45, STAFF_ID),
        ("update", venue_id, {"name": "Orchard Hall B"}),
    ]
    body = response.json()
    assert (body["setup_minutes"], body["turnaround_minutes"], body["name"]) == (
        0, 45, "Orchard Hall B"
    )


# AC6-API2 (partition): a request without times never calls update_timing
def test_other_fields_alone_are_a_plain_update(store: RecordingStore) -> None:
    venue_id = make_venue()["id"]

    response = client.patch(f"/venues/{venue_id}", json={"max_capacity": 150})

    assert response.status_code == 200
    assert store.calls == [("update", venue_id, {"max_capacity": 150})]


# AC6-API3 (negative): an unknown venue is 404 and nothing else is updated
def test_unknown_venue_time_change_is_not_found(store: RecordingStore) -> None:
    response = client.patch(
        f"/venues/{VENUE_ID}", json={"setup_minutes": 30, "name": "Ghost Hall"}
    )

    assert response.status_code == 404
    assert store.calls == [("update_timing", VENUE_ID, 30, None, STAFF_ID)]


def supabase_store(status_code: int, body: object) -> tuple[SupabaseVenueRepository, list]:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status_code, json=body)

    return SupabaseVenueRepository(
        "https://project.supabase.co", "key", transport=httpx.MockTransport(handler)
    ), sent


def venue_row(**overrides: object) -> dict:
    return {
        "id": VENUE_ID, "name": "Hall A", "location": "Level 1", "max_capacity": 200,
        "facilities": [], "accessibility_features": [], "supported_layouts": [],
        "operating_slots": ["AM"], "status": "available",
        "setup_minutes": 0, "turnaround_minutes": 45,
        "created_at": "2026-10-13T01:00:00+00:00", "updated_at": "2026-10-21T01:00:00+00:00",
    } | overrides


# AC6-API4 (happy): the Supabase store calls update_venue_timing and returns the venue
def test_supabase_store_calls_update_venue_timing() -> None:
    store, sent = supabase_store(200, {
        "venue": venue_row(), "timing_change_id": "11111111-1111-1111-1111-111111111111",
        "flagged_booking_ids": [], "unlinked_booking_ids": [],
    })

    venue = store.update_timing(VENUE_ID, None, 45, STAFF_ID)

    assert sent[0].method == "POST"
    assert sent[0].url.path == "/rest/v1/rpc/update_venue_timing"
    assert json.loads(sent[0].content) == {
        "p_venue_id": VENUE_ID, "p_setup_minutes": None,
        "p_turnaround_minutes": 45, "p_changed_by": STAFF_ID,
    }
    assert (venue.setup_minutes, venue.turnaround_minutes) == (0, 45)


# AC6-API5 (negative): P0002 is "not found"; other failures and odd bodies are errors
def test_supabase_store_maps_failures() -> None:
    assert supabase_store(404, {"code": "P0002"})[0].update_timing(VENUE_ID, 30, None, STAFF_ID) is None
    assert supabase_store(200, {})[0].update_timing("not-a-uuid", 30, None, STAFF_ID) is None
    with pytest.raises(SupabaseRepositoryError):
        supabase_store(400, {"code": "23514"})[0].update_timing(VENUE_ID, 20, None, STAFF_ID)
    with pytest.raises(SupabaseRepositoryError):
        supabase_store(200, [venue_row()])[0].update_timing(VENUE_ID, 30, None, STAFF_ID)
