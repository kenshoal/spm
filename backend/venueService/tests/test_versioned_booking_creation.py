"""SCRUM-35 membership prerequisite: real venue HTTP/client/adapter boundaries, fake remote transport only."""

from datetime import datetime

import httpx
import pytest
from booking_support import (
    COORDINATOR,
    EVENT,
    FakeEventService,
    as_user,
    make_venue,
    submit_body,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.booking_models import BookingRequest
from app.booking_repository import get_booking_repository
from app.event_requests import EventRequestClient
from app.main import app
from app.supabase_booking_repository import SupabaseBookingRepository

VERSION = "2026-10-22T08:00:00+08:00"
EXPECTED_VERSION = datetime.fromisoformat("2026-10-22T00:00:00+00:00")
AUTH = {"Authorization": "Bearer coordinator-test-token"}
MISSING = object()


def event_client(version: object) -> EventRequestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/coordinator"):
            return httpx.Response(200, json={"coordinator_id": COORDINATOR})
        body = {"event_name": "Current event", "expected_attendance": 55, "venue_requirements": "Stage"}
        if version is not MISSING:
            body["updated_at"] = version
        return httpx.Response(200, json=body)

    return EventRequestClient("http://events.test", transport=httpx.MockTransport(handler))


# AC3-X12 (cross-cutting): an aware event version survives the real client as an instant, ready for mutation-time checking.
def test_event_snapshot_carries_aware_version() -> None:
    snapshot = event_client(VERSION).snapshot_for_coordinator(EVENT, "token", COORDINATOR)

    assert getattr(snapshot, "updated_at", None) == EXPECTED_VERSION
    assert (snapshot.event_name, snapshot.expected_attendance, snapshot.venue_requirements) == (
        "Current event", 55, "Stage",
    )


# AC3-N15, AC3-N16, AC3-N17 (negative): an absent, malformed or timezone-naive version cannot silently enable an unchecked booking write.
@pytest.mark.parametrize(
    "version", [MISSING, "not-a-timestamp", "2026-10-22T08:00:00"],
    ids=["AC3-N15", "AC3-N16", "AC3-N17"],
)
def test_unusable_event_version_is_safe_502(version: object) -> None:
    with pytest.raises(HTTPException) as error:
        event_client(version).snapshot_for_coordinator(EVENT, "token", COORDINATOR)

    assert (error.value.status_code, error.value.detail) == (502, "Event request service unavailable")


class RecordingStore:
    """Records the internal call only; it implements no assignment/version rules."""

    def __init__(self) -> None:
        self.calls: list[tuple[BookingRequest, datetime | None]] = []

    def create(self, booking: BookingRequest, expected_event_updated_at: datetime | None = None) -> BookingRequest:
        self.calls.append((booking, expected_event_updated_at))
        return booking

    def list_approved_for_venue(self, venue_id, start_date, end_date) -> list[BookingRequest]:
        # The clash warning (SCRUM-67) reads approved bookings; this store holds none.
        return []


def prepare_route() -> tuple[dict, FakeEventService]:
    events = FakeEventService()
    events.add_event()
    events.events[EVENT]["updated_at"] = VERSION
    as_user(COORDINATOR, "event_coordinator", events=events)
    return submit_body(make_venue().id), events


# AC3-X13 (cross-cutting): the public payload stays unchanged while the verified event version reaches the storage boundary internally.
def test_creation_route_forwards_snapshot_version() -> None:
    body, _ = prepare_route()
    store = RecordingStore()
    app.dependency_overrides[get_booking_repository] = lambda: store

    response = TestClient(app).post("/booking-requests", json=body, headers=AUTH)

    assert response.status_code == 201
    saved = response.json()
    assert (saved["status"], saved["requested_by"], saved["event_request_id"]) == ("pending", COORDINATOR, EVENT)
    assert (saved["start_minute"], saved["end_minute"]) == (420, 720)
    assert len(store.calls) == 1
    booking, version = store.calls[0]
    assert booking.venue_id == body["venue_id"]
    assert version == EXPECTED_VERSION
    assert "updated_at" not in saved and "expected_event_updated_at" not in saved


# AC3-N18, AC2-N7, AC2-N8 (negative): the real adapter's current-version/assignment refusals map safely to public conflict/not-found without a direct-insert fallback.
@pytest.mark.parametrize(
    ("sqlstate", "status", "detail"),
    [("P0004", 409, "Event request changed; refresh before booking"),
     ("P0002", 404, "Event request not found"), ("P0003", 404, "Event request not found")],
    ids=["AC3-N18", "AC2-N7", "AC2-N8"],
)
def test_native_creation_refusal_is_publicly_mapped(sqlstate: str, status: int, detail: str) -> None:
    body, _ = prepare_route()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(400, json={"code": sqlstate, "message": "private database detail"})

    repo = SupabaseBookingRepository("https://project.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_booking_repository] = lambda: repo
    response = TestClient(app).post("/booking-requests", json=body, headers=AUTH)

    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/rest/v1/rpc/create_event_venue_booking_request"
