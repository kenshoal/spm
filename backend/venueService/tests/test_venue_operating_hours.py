"""Per-venue daily operating hours (hotfix 2, H12).

SCRUM-30 AC1, AC2, AC6 (the catalogue), AC4 (search), AC5 (suitability); SCRUM-31 AC4
(the calendar); SCRUM-12 AC3. A venue has one daily operating start and end, on 15-minute
steps within 07:00 to 24:00 (420 to 1440 minutes). Time outside them is never free.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

import httpx
import pytest
from booking_support import (
    COORDINATOR,
    EVENT,
    OTHER_EVENT,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    seed_booking,
)
from fastapi.testclient import TestClient

from app.block_models import BlockReason, VenueBlockCreate
from app.block_repository import block_repository
from app.booking_models import BookingRequestStatus
from app.booking_repository import booking_repository
from app.dependencies import require_venue_staff
from app.hold_store import memory_hold_store
from app.main import app
from app.models import VenueCreate, VenueUpdate
from app.repository import repository
from app.supabase_repository import SupabaseVenueRepository

client = TestClient(app)
DAY = "2026-10-05"


@pytest.fixture(autouse=True)
def _as_staff() -> None:
    as_user(STAFF, "venue_staff")
    yield
    app.dependency_overrides.pop(require_venue_staff, None)


def body(**overrides) -> dict:
    return {"name": "Hours Hall", "location": "Campus", "max_capacity": 80, **overrides}


def search(**params) -> list[str]:
    response = client.get("/venues/search", params=params)
    assert response.status_code == 200, response.text
    return [venue["id"] for venue in response.json()]


def open_venue(start: int, end: int, **extra):
    venue = make_venue(name=extra.pop("name", f"Open {start}-{end}"))
    return repository.update(venue.id, VenueUpdate(operating_start_minute=start, operating_end_minute=end, **extra))


# ---- the catalogue (SCRUM-30 AC1, AC2, AC6) ----------------------------------------------


# AC1-H1 (happy): a venue is created with its daily operating start and end
def test_a_venue_is_created_with_its_operating_hours() -> None:
    response = client.post("/venues", json=body(operating_start_minute=540, operating_end_minute=1080))

    assert response.status_code == 201
    assert (response.json()["operating_start_minute"], response.json()["operating_end_minute"]) == (540, 1080)
    assert client.get(f"/venues/{response.json()['id']}").json()["operating_start_minute"] == 540


# AC1-P1 (partition): a venue created without hours operates 07:00 to 24:00
def test_a_venue_without_hours_operates_the_full_day() -> None:
    created = client.post("/venues", json=body()).json()

    assert (created["operating_start_minute"], created["operating_end_minute"]) == (420, 1440)


# AC1-B1, AC1-B2 (boundary): the first and last quarter hours of the day are valid, each alone
@pytest.mark.parametrize("hours", [(420, 435), (1425, 1440), (420, 1440)], ids=["AC1-B1", "AC1-B2", "AC1-B3"])
def test_the_edges_of_the_day_are_valid(hours: tuple[int, int]) -> None:
    response = client.post("/venues", json=body(operating_start_minute=hours[0], operating_end_minute=hours[1]))

    assert response.status_code == 201


# AC6-N1 to AC6-N6 (negative): an invalid operating range is refused and nothing is stored
@pytest.mark.parametrize(
    "hours",
    [(405, 1080), (540, 1455), (545, 1080), (540, 1085), (600, 600), (900, 600)],
    ids=["AC6-N1", "AC6-N2", "AC6-N3", "AC6-N4", "AC6-N5", "AC6-N6"],
)
def test_an_invalid_range_is_refused(hours: tuple[int, int]) -> None:
    before = len(repository.list())

    response = client.post("/venues", json=body(operating_start_minute=hours[0], operating_end_minute=hours[1]))

    assert response.status_code == 422
    assert len(repository.list()) == before


# AC2-H1 (happy): an update can change either end, and an omitted end keeps its value
def test_an_update_changes_one_end_and_keeps_the_other() -> None:
    venue = open_venue(540, 1080)

    only_start = client.patch(f"/venues/{venue.id}", json={"operating_start_minute": 600}).json()
    both = client.patch(f"/venues/{venue.id}", json={"operating_start_minute": 480, "operating_end_minute": 1200}).json()

    assert (only_start["operating_start_minute"], only_start["operating_end_minute"]) == (600, 1080)
    assert (both["operating_start_minute"], both["operating_end_minute"]) == (480, 1200)


# AC2-P1 (partition): an update of other attributes leaves the hours alone
def test_an_update_of_another_attribute_keeps_the_hours() -> None:
    venue = open_venue(540, 1080)

    updated = client.patch(f"/venues/{venue.id}", json={"max_capacity": 120}).json()

    assert (updated["operating_start_minute"], updated["operating_end_minute"]) == (540, 1080)


# AC6-N7 (negative): an update that leaves the stored range invalid is refused and changes nothing
@pytest.mark.parametrize(
    "patch",
    [{"operating_start_minute": 1100}, {"operating_end_minute": 500}, {"operating_start_minute": 1080}],
    ids=["AC6-N7", "AC6-N8", "AC6-N9"],
)
def test_an_update_that_crosses_the_other_end_is_refused(patch: dict) -> None:
    venue = open_venue(540, 1080)

    response = client.patch(f"/venues/{venue.id}", json=patch)

    assert response.status_code == 422
    stored = repository.get(venue.id)
    assert (stored.operating_start_minute, stored.operating_end_minute) == (540, 1080)


# AC6-N10 (negative): an update cannot clear an end with null
def test_an_update_cannot_send_null_hours() -> None:
    venue = open_venue(540, 1080)

    response = client.patch(f"/venues/{venue.id}", json={"operating_end_minute": None})

    assert response.status_code == 422


# AC7-N1 (negative): only Venue Staff change the hours
def test_a_coordinator_cannot_change_the_hours() -> None:
    venue = open_venue(540, 1080)
    as_user(COORDINATOR, "event_coordinator")

    response = client.patch(f"/venues/{venue.id}", json={"operating_start_minute": 600})

    assert response.status_code == 403
    assert repository.get(venue.id).operating_start_minute == 540


# ---- search (SCRUM-30 AC4) ---------------------------------------------------------------


# AC4-H1, AC4-B1..B4 (boundary): a venue is offered only for a time wholly inside its hours
@pytest.mark.parametrize(
    ("start", "end", "offered"),
    [(540, 600, True), (1020, 1080, True), (525, 585, False), (1050, 1095, False), (480, 540, False), (1080, 1140, False)],
    ids=["AC4-H1", "AC4-B1", "AC4-B2", "AC4-B3", "AC4-B4", "AC4-B5"],
)
def test_search_offers_a_venue_only_inside_its_hours(start: int, end: int, offered: bool) -> None:
    venue = open_venue(540, 1080)

    assert (venue.id in search(date=DAY, start_minute=start, end_minute=end)) is offered


# AC4-P1 (partition): a search by date alone needs free time inside the hours, not outside them
def test_a_date_only_search_needs_free_time_inside_the_hours() -> None:
    venue = open_venue(540, 600)  # one hour a day
    seed_booking(
        venue_id=venue.id, start_date=date.fromisoformat(DAY), end_date=date.fromisoformat(DAY),
        start_minute=540, end_minute=600, status=BookingRequestStatus.APPROVED, decided_by=STAFF,
    )

    assert venue.id not in search(date=DAY)
    assert venue.id in search(date="2026-10-06")


# AC4-P2 (partition): the hours decide the search with no other filter, and the other filters still apply
def test_other_filters_still_apply_to_a_venue_open_at_that_time() -> None:
    venue = open_venue(540, 1080)

    assert venue.id in search(date=DAY, start_minute=600, end_minute=660, required_capacity=10)
    assert venue.id not in search(date=DAY, start_minute=600, end_minute=660, required_capacity=1000)


# ---- the availability check (SCRUM-66 AC1) ----------------------------------------------


def check(venue_id: str, start: int, end: int):
    return client.post(
        f"/venues/{venue_id}/availability",
        json={"start_date": DAY, "end_date": DAY, "start_minute": start, "end_minute": end},
    )


# AC4-N1 (negative): the availability check reports a time outside the hours, and a time inside is available
def test_the_availability_check_reports_a_time_outside_the_hours() -> None:
    venue = open_venue(540, 1080)
    as_user(COORDINATOR, "event_coordinator")

    outside = check(venue.id, 480, 600).json()
    inside = check(venue.id, 540, 600).json()

    assert outside["available"] is False and "outside_operating_hours" in outside["reasons"]
    assert inside["available"] is True and inside["reasons"] == []


# ---- suitability (SCRUM-30 AC5, SCRUM-12 AC3) --------------------------------------------


def suitability(venue_id: str, **extra):
    return client.post(f"/venues/{venue_id}/suitability", json={"expected_attendance": 10, **extra})


# AC5-H1, AC5-N1 (happy and negative): a requested time inside the hours is suitable; outside is not, and says why
def test_suitability_judges_the_requested_time_against_the_hours() -> None:
    venue = open_venue(540, 1080)
    as_user(COORDINATOR, "event_coordinator")

    inside = suitability(venue.id, required_start_minute=600, required_end_minute=660).json()
    outside = suitability(venue.id, required_start_minute=480, required_end_minute=600).json()

    assert inside["suitable"] is True
    assert outside["suitable"] is False
    [mismatch] = outside["mismatches"]
    assert mismatch["attribute"] == "operating_hours"
    assert "09:00" in mismatch["reason"] and "18:00" in mismatch["reason"]


# AC5-P1 (partition): with no time asked for, the hours are not judged
def test_suitability_without_a_time_does_not_judge_the_hours() -> None:
    venue = open_venue(540, 1080)
    as_user(COORDINATOR, "event_coordinator")

    assert suitability(venue.id).json()["suitable"] is True


# ---- the calendar (SCRUM-31 AC4) ---------------------------------------------------------


def calendar(venue_id: str):
    return client.get(f"/venues/{venue_id}/calendar", params={"month": "2026-10"}).json()


def day_of(body: dict, text: str) -> dict:
    return next(item for item in body["days"] if item["date"] == text)


# AC4-H2 (happy): free time is inside the hours only; nothing outside them is free
def test_the_calendar_shows_free_time_only_inside_the_hours() -> None:
    venue = open_venue(540, 1080)
    as_user(COORDINATOR, "event_coordinator")

    free = [(r["start_minute"], r["end_minute"]) for r in day_of(calendar(venue.id), DAY)["free"]]

    assert free == [(540, 1080)]


# AC4-P3 (partition): bookings and blocks are still listed, and free time is what is left of the hours
def test_the_calendar_subtracts_bookings_from_the_hours() -> None:
    venue = open_venue(540, 1080)
    seed_booking(
        venue_id=venue.id, start_date=date.fromisoformat(DAY), end_date=date.fromisoformat(DAY),
        start_minute=600, end_minute=720, status=BookingRequestStatus.APPROVED, decided_by=STAFF,
    )
    block_repository.create(
        venue.id,
        VenueBlockCreate(
            start_date=date.fromisoformat(DAY), end_date=date.fromisoformat(DAY), start_minute=420, end_minute=480,
            reason_category=BlockReason.MAINTENANCE, reason_detail="x",
        ),
        created_by=STAFF,
    )
    as_user(COORDINATOR, "event_coordinator")

    item = day_of(calendar(venue.id), DAY)

    assert [(r["start_minute"], r["end_minute"]) for r in item["free"]] == [(540, 600), (720, 1080)]
    assert ("blocked", 420, 480) in {(e["state"], e["start_minute"], e["end_minute"]) for e in item["entries"]}


# AC4-X1 (cross-cutting): a venue's calendar and its search agree at every 15-minute step
def test_the_calendar_and_search_agree_for_a_venue_with_short_hours() -> None:
    venue = open_venue(600, 1020)
    seed_booking(
        venue_id=venue.id, start_date=date.fromisoformat(DAY), end_date=date.fromisoformat(DAY),
        start_minute=720, end_minute=780, status=BookingRequestStatus.APPROVED, decided_by=STAFF,
    )
    as_user(COORDINATOR, "event_coordinator")
    item = day_of(calendar(venue.id), DAY)

    for start in range(420, 1440, 15):
        found = venue.id in search(date=DAY, start_minute=start, end_minute=start + 15)
        in_calendar = any(r["start_minute"] <= start and start + 15 <= r["end_minute"] for r in item["free"])
        assert found == in_calendar, start


# AC4-X2 (cross-cutting): the day with short hours is an ordered, non-overlapping list inside the hours
def test_calendar_ranges_stay_inside_the_hours() -> None:
    venue = open_venue(600, 1020)
    as_user(COORDINATOR, "event_coordinator")

    for item in calendar(venue.id)["days"]:
        ranges = sorted((r["start_minute"], r["end_minute"]) for r in item["free"])
        assert all(600 <= start and end <= 1020 for start, end in ranges)
        assert all(a_end <= b_start for (_, a_end), (b_start, _) in pairwise(ranges))


# ---- the store (SCRUM-30 AC1, AC2) -------------------------------------------------------


def supabase(handler) -> SupabaseVenueRepository:
    return SupabaseVenueRepository("https://example.supabase.co", "secret", httpx.MockTransport(handler))


# AC1-X1 (cross-cutting): the Supabase store sends the hours on create and on update
def test_the_supabase_store_sends_the_hours() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        row = {
            "id": "00000000-0000-4000-8000-000000000001", "name": "x", "location": "y", "max_capacity": 5,
            "operating_start_minute": 540, "operating_end_minute": 1080,
            "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z",
        }
        return httpx.Response(200, json=[row])

    store = supabase(handler)
    created = store.create(VenueCreate(name="x", location="y", max_capacity=5, operating_start_minute=540, operating_end_minute=1080))
    store.update("00000000-0000-4000-8000-000000000001", VenueUpdate(operating_end_minute=1200))

    import json as _json

    assert _json.loads(seen[0].content)["operating_start_minute"] == 540
    assert _json.loads(seen[0].content)["operating_end_minute"] == 1080
    assert _json.loads(seen[1].content)["operating_end_minute"] == 1200
    assert "operating_start_minute" not in _json.loads(seen[1].content)
    assert (created.operating_start_minute, created.operating_end_minute) == (540, 1080)


# ---- holds and approval refuse time outside the hours (SCRUM-30 AC4; review E1) -----------


def place_hold(venue_id: str, start: int, end: int) -> httpx.Response:
    events = FakeEventService()
    events.add_event()
    as_user(COORDINATOR, "event_coordinator", events=events)
    return client.post(
        f"/venues/{venue_id}/holds",
        json={
            "event_request_id": EVENT,
            "start_date": "2030-03-04",
            "end_date": "2030-03-04",
            "start_minute": start,
            "end_minute": end,
            "expires_at": (datetime.now(UTC) + timedelta(hours=48)).isoformat(),
        },
    )


# AC4-N2 (negative): a hold outside the hours is refused with outside_operating_hours and nothing is stored
def test_a_hold_outside_the_hours_is_refused_with_its_code() -> None:
    venue = open_venue(540, 1080)

    response = place_hold(venue.id, 480, 600)

    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["outside_operating_hours"]
    assert memory_hold_store.list_for_event(EVENT) == []


# AC4-B5 (boundary): a hold that starts exactly when the venue opens and ends when it closes is placed
def test_a_hold_across_exactly_the_hours_is_placed() -> None:
    venue = open_venue(540, 1080)

    assert place_hold(venue.id, 540, 1080).status_code == 201


# AC4-N3 (negative): approving a request outside the hours is refused with the code, the request stays pending
def test_approval_outside_the_hours_is_refused_with_its_code() -> None:
    venue = open_venue(540, 1080)
    request = seed_booking(
        venue_id=venue.id, event_request_id=OTHER_EVENT, start_date=date(2030, 3, 4), end_date=date(2030, 3, 4),
        start_minute=480, end_minute=600,
    )
    as_user(STAFF, "venue_staff")

    response = client.post(f"/booking-requests/{request.id}/decision", json={"decision": "approved"})

    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["outside_operating_hours"]
    assert booking_repository.get(request.id).status is BookingRequestStatus.PENDING
    refusals = client.get(f"/booking-requests/{request.id}/refusals").json()
    assert [r["refusal_codes"] for r in refusals] == [["outside_operating_hours"]]


# AC4-H3 (happy): approving a request inside the hours still works
def test_approval_inside_the_hours_is_approved() -> None:
    venue = open_venue(540, 1080)
    request = seed_booking(
        venue_id=venue.id, event_request_id=OTHER_EVENT, start_date=date(2030, 3, 4), end_date=date(2030, 3, 4),
        start_minute=540, end_minute=600,
    )
    as_user(STAFF, "venue_staff")

    response = client.post(f"/booking-requests/{request.id}/decision", json={"decision": "approved"})

    assert response.status_code == 200, response.text
    assert booking_repository.get(request.id).status is BookingRequestStatus.APPROVED
