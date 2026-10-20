"""SCRUM-65 slice 2: blocks, search, availability checks and suitability on times.

Case IDs match docs/testcases/scrum_65_testcases.md. Times are minutes after
midnight (07:00 = 420, 24:00 = 1440). The conftest caller is Venue Staff.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import booking_decision_store
from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_notifications import current_venue_date, get_booking_notifier
from app.booking_repository import booking_repository
from app.main import app

client = TestClient(app)
DAY = "2030-03-04"


def hm(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


@pytest.fixture(autouse=True)
def _clear_refusals():
    booking_decision_store.memory_decision_store.clear()
    yield
    booking_decision_store.memory_decision_store.clear()


def make_venue(**overrides) -> str:
    body = {"name": "Hall", "location": "Campus", "max_capacity": 50} | overrides
    response = client.post("/venues", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def block_body(start: str, end: str, first: str = DAY, last: str = DAY) -> dict:
    return {
        "start_date": first,
        "end_date": last,
        "start_minute": hm(start),
        "end_minute": hm(end),
        "reason_category": "maintenance",
    }


def make_block(venue_id: str, start: str, end: str, **dates) -> dict:
    response = client.post(f"/venues/{venue_id}/blocks", json=block_body(start, end, **dates))
    assert response.status_code == 201, response.text
    return response.json()


def seed_booking(venue_id: str, start: str, end: str, *, approved: bool, day: str = DAY) -> str:
    booking = booking_repository.create(
        BookingRequest(
            venue_id=venue_id,
            requested_by=str(uuid4()),
            event_request_id=str(uuid4()),
            start_date=date.fromisoformat(day),
            end_date=date.fromisoformat(day),
            start_minute=hm(start),
            end_minute=hm(end),
        )
    )
    if approved:
        booking.status = BookingRequestStatus.APPROVED
    return booking.id


def search(**params) -> list[str]:
    response = client.get("/venues/search", params=params)
    assert response.status_code == 200, response.text
    return [venue["id"] for venue in response.json()]


def error_types(response) -> list[str]:
    return [error["type"] for error in response.json()["detail"]]


# --- AC3: blocks use start and end times -----------------------------------


# AC3-H1 (happy): Venue Staff block a venue for a time range
def test_block_stores_its_times() -> None:
    venue = make_venue()

    block = make_block(venue, "12:30", "14:00")

    assert (block["start_minute"], block["end_minute"]) == (750, 840)
    assert block["slots"] == ["PM"]
    assert block["status"] == "active"


# AC3-N1 (negative): invalid block times are refused with the reason
@pytest.mark.parametrize(
    ("start", "end", "code"),
    [
        ("12:10", "14:00", "off_step"),
        ("06:45", "08:00", "outside_operating_window"),
        ("14:00", "14:00", "end_not_after_start"),
    ],
)
def test_invalid_block_times_are_refused(start: str, end: str, code: str) -> None:
    venue = make_venue()

    response = client.post(f"/venues/{venue}/blocks", json=block_body(start, end))

    assert response.status_code == 422
    assert code in error_types(response)
    assert client.get(f"/venues/{venue}/blocks").json() == []


# AC3-N2 (negative): the retired slots field is refused
def test_block_slots_field_is_refused() -> None:
    venue = make_venue()
    body = block_body("12:00", "14:00") | {"slots": ["PM"]}

    response = client.post(f"/venues/{venue}/blocks", json=body)

    assert response.status_code == 422


# AC3-B1 (boundary): approval is refused by a block it overlaps by one step,
# and allowed right up to the block's start
@pytest.mark.parametrize(
    ("start", "end", "refused"),
    [("11:00", "12:45", True), ("11:00", "12:30", False), ("14:00", "15:00", False)],
)
def test_block_refuses_approval_by_time(start: str, end: str, refused: bool) -> None:
    venue = make_venue()
    make_block(venue, "12:30", "14:00")
    booking = seed_booking(venue, start, end, approved=False)

    response = client.post(
        f"/booking-requests/{booking}/decision", json={"decision": "approved"}
    )

    if refused:
        assert response.status_code == 409
        assert response.json()["detail"]["refusal_codes"] == ["active_block"]
        assert booking_repository.get(booking).status is BookingRequestStatus.PENDING
    else:
        assert response.status_code == 200


# AC3-H2 (happy): a blocked time is not offered in search; other times that day are
def test_blocked_time_is_not_offered_in_search() -> None:
    venue = make_venue()
    make_block(venue, "12:30", "14:00")

    assert venue not in search(date=DAY, start_minute=hm("13:00"), end_minute=hm("15:00"))
    assert venue in search(date=DAY, start_minute=hm("14:00"), end_minute=hm("16:00"))


# AC3-X1 (cross-cutting): a new block alerts only bookings it overlaps in time,
# and the notice carries both time ranges
def test_block_notice_uses_times() -> None:
    venue = make_venue()
    hit = seed_booking(venue, "13:00", "15:00", approved=True)
    seed_booking(venue, "09:00", "12:30", approved=True)
    sent: list[dict] = []

    class Spy:
        def send(self, event: dict) -> None:
            sent.append(event)

    app.dependency_overrides[get_booking_notifier] = lambda: Spy()
    app.dependency_overrides[current_venue_date] = lambda: date(2030, 3, 1)
    try:
        make_block(venue, "12:30", "14:00")
    finally:
        app.dependency_overrides.pop(get_booking_notifier, None)
        app.dependency_overrides.pop(current_venue_date, None)

    assert [event["payload"]["booking_request_id"] for event in sent] == [hit]
    payload = sent[0]["payload"]
    assert (payload["block_start_minute"], payload["block_end_minute"]) == (750, 840)
    assert (payload["booking_start_minute"], payload["booking_end_minute"]) == (780, 900)


# --- AC4: search, the availability check and suitability on date and time --


# AC4-H1 (happy): search hides a venue booked at an overlapping time only
def test_search_respects_booked_times() -> None:
    venue = make_venue()
    seed_booking(venue, "10:00", "12:00", approved=True)
    seed_booking(venue, "15:00", "17:00", approved=False)

    assert venue not in search(date=DAY, start_minute=hm("11:00"), end_minute=hm("13:00"))
    assert venue in search(date=DAY, start_minute=hm("12:00"), end_minute=hm("14:00"))
    # A pending booking reserves nothing.
    assert venue in search(date=DAY, start_minute=hm("15:00"), end_minute=hm("16:00"))


# AC4-B1 (boundary): with only a date, a venue needs some free time that day
def test_search_by_date_needs_free_time() -> None:
    full = make_venue(name="Full")
    almost = make_venue(name="Almost")
    make_block(full, "07:00", "13:00")
    seed_booking(full, "13:00", "24:00", approved=True)
    make_block(almost, "07:00", "23:45")

    found = search(date=DAY)

    assert full not in found
    assert almost in found


# AC4-N1 (negative): invalid search times, or times without a date, are refused
@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"date": DAY, "start_minute": 610, "end_minute": 720}, "off_step"),
        ({"date": DAY, "start_minute": 405, "end_minute": 480}, "outside_operating_window"),
        ({"date": DAY, "start_minute": 720, "end_minute": 720}, "end_not_after_start"),
        ({"date": DAY, "start_minute": 600}, "times_incomplete"),
        ({"start_minute": 600, "end_minute": 720}, "date_required"),
    ],
)
def test_invalid_search_times_are_refused(params: dict, code: str) -> None:
    make_venue()

    response = client.get("/venues/search", params=params)

    assert response.status_code == 422
    assert code in error_types(response)


# AC4-H2 (happy): the availability check reports the overlapping part in time
def test_availability_check_uses_times() -> None:
    venue = make_venue()
    block = make_block(venue, "12:30", "14:00")
    booking = seed_booking(venue, "10:00", "13:00", approved=True)

    response = client.post(
        f"/venues/{venue}/availability",
        json={"start_date": DAY, "end_date": DAY, "start_minute": hm("12:00"),
              "end_minute": hm("15:00")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reasons"] == ["active_block", "booking_conflict"]
    [conflict] = body["conflicts"]
    assert (conflict["block_id"], conflict["start_minute"], conflict["end_minute"]) == (
        block["id"], 750, 840)
    [overlap] = body["booking_conflicts"]
    assert (overlap["booking_id"], overlap["start_minute"], overlap["end_minute"]) == (
        booking, 720, 780)


# AC4-P1 (partition): a time free of blocks and bookings is available
def test_availability_check_free_time() -> None:
    venue = make_venue()
    make_block(venue, "12:30", "14:00")

    response = client.post(
        f"/venues/{venue}/availability",
        json={"start_date": DAY, "end_date": DAY, "start_minute": hm("14:00"),
              "end_minute": hm("16:00")},
    )

    assert response.json()["available"] is True
    assert response.json()["reasons"] == []


# AC4-H3 (happy): suitability takes a time range inside the operating window
@pytest.mark.parametrize(
    ("start", "end", "suitable"),
    [("07:00", "24:00", True), ("10:00", "12:00", True)],
)
def test_suitability_accepts_times(start: str, end: str, suitable: bool) -> None:
    venue = make_venue()

    response = client.post(
        f"/venues/{venue}/suitability",
        json={"expected_attendance": 10, "required_start_minute": hm(start),
              "required_end_minute": hm(end)},
    )

    assert response.status_code == 200
    assert response.json()["suitable"] is suitable


# AC4-N2 (negative): suitability refuses invalid times and the retired slot
@pytest.mark.parametrize(
    "body",
    [
        {"required_start_minute": 360, "required_end_minute": 480},
        {"required_start_minute": 610, "required_end_minute": 720},
        {"required_start_minute": 600},
        {"required_slot": "AM"},
    ],
)
def test_suitability_refuses_invalid_times(body: dict) -> None:
    venue = make_venue()

    response = client.post(
        f"/venues/{venue}/suitability", json={"expected_attendance": 10} | body
    )

    assert response.status_code == 422
