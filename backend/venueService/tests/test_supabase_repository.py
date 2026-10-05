"""SupabaseVenueRepository against a fake Data API (no network), plus storage
selection and configuration."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app
from app.models import RoomLayout, Slot, VenueCreate, VenueStatus, VenueUpdate
from app.repository import _supabase_repository, get_repository, repository
from app.supabase_repository import SupabaseRepositoryError, SupabaseVenueRepository

URL = "https://project.supabase.co"
KEY = "sb_secret_test"
VENUE_ID = "2a192261-5e90-4398-90ff-1a2d0eaaff00"
OTHER_ID = "11111111-1111-1111-1111-111111111111"
BOOKING_ID = "33333333-3333-3333-3333-333333333333"


def _row(**overrides: object) -> dict:
    row = {
        "id": VENUE_ID,
        "name": "Hall A",
        "location": "Level 1",
        "max_capacity": 200,
        "facilities": ["projector"],
        "accessibility_features": ["ramp"],
        "supported_layouts": ["theatre"],
        "operating_slots": ["AM", "PM"],
        "status": "available",
        "created_at": "2026-09-28T01:00:00+00:00",
        "updated_at": "2026-09-28T01:00:00+00:00",
    }
    row.update(overrides)
    return row


def _booking_row(**overrides: object) -> dict:
    """A venue_booking_requests row as SCRUM-32's 0018 migration defines it."""
    row = {
        "id": BOOKING_ID,
        "venue_id": VENUE_ID,
        "requested_by": OTHER_ID,
        "event_request_id": OTHER_ID,
        "event_name": "Acme Summit",
        "expected_attendance": 120,
        "requirements_note": "Wheelchair access required",
        "start_date": "2026-10-10",
        "end_date": "2026-10-11",
        "slots": ["AM", "PM"],
        "status": "pending",
        "decision_reason": None,
        "suggested_alternative": None,
        "decided_by": None,
        "decided_at": None,
        "created_at": "2026-10-04T01:00:00+00:00",
    }
    row.update(overrides)
    return row


class FakeDataAPI:
    """Records requests and replies with a canned response."""

    def __init__(self, status_code: int = 200, body: object = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status_code = status_code
        self.body = [] if body is None else body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.body)

    def repo(self) -> SupabaseVenueRepository:
        return SupabaseVenueRepository(URL, KEY, transport=httpx.MockTransport(self))


def test_create_inserts_full_record_and_returns_stored_row() -> None:
    api = FakeDataAPI(201, [_row()])

    venue = api.repo().create(
        VenueCreate(
            name="Hall A",
            location="Level 1",
            max_capacity=200,
            facilities=["projector"],
            accessibility_features=["ramp"],
            supported_layouts=[RoomLayout.THEATRE],
            operating_slots=[Slot.AM, Slot.PM],
        )
    )

    request = api.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/rest/v1/venues"
    assert request.headers["apikey"] == KEY
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["Prefer"] == "return=representation"
    sent = json.loads(request.content)
    assert sent["name"] == "Hall A"
    assert sent["supported_layouts"] == ["theatre"]
    assert sent["operating_slots"] == ["AM", "PM"]
    assert sent["status"] == "available"
    assert {"id", "created_at", "updated_at"} <= sent.keys()
    assert venue.id == VENUE_ID
    assert venue.supported_layouts == [RoomLayout.THEATRE]


def test_get_filters_by_id_and_decodes_row() -> None:
    api = FakeDataAPI(200, [_row(status="blocked")])

    venue = api.repo().get(VENUE_ID)

    params = api.requests[0].url.params
    assert params["id"] == f"eq.{VENUE_ID}"
    assert params["limit"] == "1"
    assert venue is not None
    assert venue.status is VenueStatus.BLOCKED


def test_get_unknown_id_returns_none() -> None:
    assert FakeDataAPI(200, []).repo().get(VENUE_ID) is None


def test_malformed_id_returns_none_without_querying() -> None:
    api = FakeDataAPI(200, [_row()])

    assert api.repo().get("not-a-uuid") is None
    assert api.repo().update("not-a-uuid", VenueUpdate(name="X")) is None
    assert api.requests == []


def test_list_returns_every_row_in_creation_order() -> None:
    api = FakeDataAPI(200, [_row(), _row(id=OTHER_ID)])

    venues = api.repo().list()

    assert api.requests[0].url.params["order"] == "created_at.asc"
    assert [v.id for v in venues] == [VENUE_ID, OTHER_ID]


# AC6-H1 (happy): Venue Staff read the SCRUM-32 booking record with its event snapshot
def test_list_booking_requests_reads_scrum32_booking_record() -> None:
    api = FakeDataAPI(200, [_booking_row()])

    bookings = api.repo().list_booking_requests()

    request = api.requests[0]
    assert request.url.path == "/rest/v1/venue_booking_requests"
    assert request.url.params["order"] == "created_at.desc"
    assert bookings[0].model_dump(mode="json") == {
        "id": BOOKING_ID,
        "venue_id": VENUE_ID,
        "event_request_id": OTHER_ID,
        "event_name": "Acme Summit",
        "expected_attendance": 120,
        "requirements_note": "Wheelchair access required",
        "start_date": "2026-10-10",
        "end_date": "2026-10-11",
        "slots": ["AM", "PM"],
        "status": "pending",
        "decision_reason": None,
        "suggested_alternative": None,
        "requested_by": OTHER_ID,
        "decided_by": None,
        "decided_at": None,
        "created_at": "2026-10-04T01:00:00Z",
    }


def test_update_sends_only_changed_fields_and_refreshes_timestamp() -> None:
    api = FakeDataAPI(200, [_row(max_capacity=300)])

    venue = api.repo().update(VENUE_ID, VenueUpdate(max_capacity=300))

    request = api.requests[0]
    assert request.method == "PATCH"
    assert request.url.params["id"] == f"eq.{VENUE_ID}"
    sent = json.loads(request.content)
    assert set(sent) == {"max_capacity", "updated_at"}
    assert sent["max_capacity"] == 300
    assert venue is not None and venue.max_capacity == 300


def test_update_unknown_id_returns_none() -> None:
    assert FakeDataAPI(200, []).repo().update(VENUE_ID, VenueUpdate(name="X")) is None


def test_error_status_raises_repository_error() -> None:
    with pytest.raises(SupabaseRepositoryError):
        FakeDataAPI(500, {"message": "boom"}).repo().list()


def test_network_failure_raises_repository_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    repo = SupabaseVenueRepository(URL, KEY, transport=httpx.MockTransport(fail))
    with pytest.raises(SupabaseRepositoryError):
        repo.list()


def test_store_failure_is_reported_as_bad_gateway() -> None:
    app.dependency_overrides[get_repository] = FakeDataAPI(500, {}).repo

    response = TestClient(app).get("/venues")

    assert response.status_code == 502
    assert response.json() == {"detail": "Venue store request failed (500)"}


def test_memory_backend_is_the_default() -> None:
    assert get_settings().venue_storage_backend == "memory"
    assert get_repository() is repository


def test_supabase_backend_selects_supabase_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VENUE_STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", KEY)
    get_settings.cache_clear()
    _supabase_repository.cache_clear()

    assert isinstance(get_repository(), SupabaseVenueRepository)
    assert get_repository() is get_repository()


def test_supabase_backend_requires_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings(venue_storage_backend="supabase", _env_file=None)


def test_supabase_backend_rejects_publishable_key() -> None:
    with pytest.raises(ValidationError):
        Settings(
            venue_storage_backend="supabase",
            supabase_url=URL,
            supabase_secret_key="sb_publishable_abc",
            _env_file=None,
        )
