"""SCRUM-59: Venue Staff set each venue's setup and turnaround time.

Case IDs match docs/testcases/scrum_59_testcases.md. Times are minutes in
15-minute increments from 0 to 1020 (Week 7 Change #1; discussion #131).
"""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.block_repository import block_repository
from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import booking_repository
from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app
from app.models import VenueCreate, VenueUpdate
from app.repository import repository
from app.supabase_repository import SupabaseVenueRepository

client = TestClient(app)


def venue_body(**overrides: object) -> dict:
    return {"name": "Orchard Hall", "location": "Orchard", "max_capacity": 100} | overrides


def make_venue(**overrides: object) -> dict:
    response = client.post("/venues", json=venue_body(**overrides))
    assert response.status_code == 201
    return response.json()


def signed_in_as(role: str) -> None:
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000009", roles=(role,)
    )
    app.dependency_overrides.pop(require_venue_staff, None)


# AC1-H1 (happy): Venue Staff create a venue with both times and they are stored
def test_create_venue_stores_setup_and_turnaround() -> None:
    body = make_venue(setup_minutes=30, turnaround_minutes=45)

    assert body["setup_minutes"] == 30
    assert body["turnaround_minutes"] == 45
    stored = repository.get(body["id"])
    assert stored.setup_minutes == 30
    assert stored.turnaround_minutes == 45


# AC1-H2 (happy): Venue Staff change both times and nothing else changes
def test_update_changes_both_times_only() -> None:
    created = make_venue(setup_minutes=30, turnaround_minutes=45)

    response = client.patch(
        f"/venues/{created['id']}", json={"setup_minutes": 0, "turnaround_minutes": 15}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["setup_minutes"] == 0
    assert body["turnaround_minutes"] == 15
    assert body["updated_at"] > created["updated_at"]
    unchanged = {k: v for k, v in body.items() if k not in {
        "setup_minutes", "turnaround_minutes", "updated_at"
    }}
    assert unchanged == {k: created[k] for k in unchanged}


# AC1-P1 (partition): changing one time keeps the other
@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"setup_minutes": 60}, (60, 45)),
        ({"turnaround_minutes": 90}, (30, 90)),
    ],
)
def test_update_one_time_keeps_the_other(patch: dict, expected: tuple[int, int]) -> None:
    created = make_venue(setup_minutes=30, turnaround_minutes=45)

    body = client.patch(f"/venues/{created['id']}", json=patch).json()

    assert (body["setup_minutes"], body["turnaround_minutes"]) == expected


# AC1-B1 (boundary): 0, 15, 1005 and 1020 are accepted for either time
@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
@pytest.mark.parametrize("minutes", [0, 15, 1005, 1020])
def test_valid_times_at_and_next_to_the_limits(field: str, minutes: int) -> None:
    assert make_venue(**{field: minutes})[field] == minutes


# AC1-N1 (negative, boundary): out-of-range and off-step times are refused
@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
@pytest.mark.parametrize("minutes", [-15, -1, 1, 14, 20, 1021, 1035])
def test_invalid_times_are_refused_on_create(field: str, minutes: int) -> None:
    response = client.post("/venues", json=venue_body(**{field: minutes}))

    assert response.status_code == 422
    assert repository.list() == []


# AC1-N2 (negative): non-numbers, null and off-step values are refused on update
@pytest.mark.parametrize("field", ["setup_minutes", "turnaround_minutes"])
@pytest.mark.parametrize("value", ["thirty", None, 20])
def test_invalid_times_are_refused_on_update(field: str, value: object) -> None:
    created = make_venue(setup_minutes=30, turnaround_minutes=45)

    response = client.patch(f"/venues/{created['id']}", json={field: value})

    assert response.status_code == 422
    assert repository.get(created["id"]).model_dump(mode="json") == created


# AC1-X1 (cross-cutting): only Venue Staff can change the times
@pytest.mark.parametrize("role", ["event_coordinator", "event_organiser", "attendee"])
def test_only_venue_staff_can_change_times(role: str) -> None:
    created = make_venue(setup_minutes=30, turnaround_minutes=45)
    signed_in_as(role)

    response = client.patch(
        f"/venues/{created['id']}", json={"setup_minutes": 60, "turnaround_minutes": 60}
    )

    assert response.status_code == 403
    assert repository.get(created["id"]).model_dump(mode="json") == created


# AC1-H3 (happy): the database store sends the times and reads them back
def test_supabase_store_sends_and_reads_times() -> None:
    venue_id = "2a192261-5e90-4398-90ff-1a2d0eaaff00"
    row = {
        "id": venue_id,
        "name": "Hall A",
        "location": "Level 1",
        "max_capacity": 200,
        "facilities": [],
        "accessibility_features": [],
        "supported_layouts": [],
        "operating_slots": ["AM"],
        "status": "available",
        "setup_minutes": 30,
        "turnaround_minutes": 45,
        "created_at": "2026-10-13T01:00:00+00:00",
        "updated_at": "2026-10-13T01:00:00+00:00",
    }
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=[row])

    store = SupabaseVenueRepository(
        "https://project.supabase.co", "key", transport=httpx.MockTransport(handler)
    )

    created = store.create(
        VenueCreate(
            name="Hall A",
            location="Level 1",
            max_capacity=200,
            setup_minutes=30,
            turnaround_minutes=45,
        )
    )
    store.update(venue_id, VenueUpdate(setup_minutes=60))

    inserted = json.loads(sent[0].content)
    assert (inserted["setup_minutes"], inserted["turnaround_minutes"]) == (30, 45)
    assert set(json.loads(sent[1].content)) == {"setup_minutes", "updated_at"}
    assert (created.setup_minutes, created.turnaround_minutes) == (30, 45)


# AC2-H1 (happy): Event Coordinators see the times on detail, list and search
def test_coordinators_see_times_wherever_a_venue_is_read() -> None:
    created = make_venue(setup_minutes=30, turnaround_minutes=45)
    signed_in_as("event_coordinator")

    detail = client.get(f"/venues/{created['id']}")
    listed = client.get("/venues")
    searched = client.get("/venues/search")

    for response in (detail, listed, searched):
        assert response.status_code == 200
    for venue in (detail.json(), listed.json()[0], searched.json()[0]):
        assert venue["setup_minutes"] == 30
        assert venue["turnaround_minutes"] == 45


# AC3-H1 (happy): changing the times leaves booking requests and blocks unchanged
def test_changing_times_leaves_bookings_and_blocks_unchanged() -> None:
    venue_id = make_venue(setup_minutes=30, turnaround_minutes=45)["id"]

    def booking(status: BookingRequestStatus) -> str:
        return booking_repository.create(
            BookingRequest(
                venue_id=venue_id,
                requested_by=str(uuid4()),
                event_request_id=str(uuid4()),
                start_date=date(2026, 11, 2),
                end_date=date(2026, 11, 2),
                slots=["AM"],
                status=status,
            )
        ).id

    booking_ids = [
        booking(BookingRequestStatus.APPROVED),
        booking(BookingRequestStatus.PENDING),
    ]
    block = client.post(
        f"/venues/{venue_id}/blocks",
        json={
            "start_date": "2026-11-02",
            "end_date": "2026-11-02",
            "slots": ["PM"],
            "reason_category": "maintenance",
        },
    )
    assert block.status_code == 201
    bookings_before = [booking_repository.get(i).model_dump() for i in booking_ids]
    blocks_before = [b.model_dump() for b in block_repository.list()]

    response = client.patch(
        f"/venues/{venue_id}", json={"setup_minutes": 60, "turnaround_minutes": 60}
    )

    assert response.status_code == 200
    assert [booking_repository.get(i).model_dump() for i in booking_ids] == bookings_before
    assert [b.model_dump() for b in block_repository.list()] == blocks_before


# AC4-H1 (happy): a venue created without the times starts at 0
def test_times_default_to_zero() -> None:
    body = make_venue()

    assert body["setup_minutes"] == 0
    assert body["turnaround_minutes"] == 0
