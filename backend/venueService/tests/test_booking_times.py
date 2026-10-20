"""SCRUM-65 slice 1: bookings carry start and end times in 15-minute steps.

Case IDs match docs/testcases/scrum_65_testcases.md. Times are minutes after
midnight (07:00 = 420, 24:00 = 1440). Submission fakes eventRequestService at
the HTTP boundary; approval runs against the in-memory stores.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from booking_support import (
    COORDINATOR,
    FakeEventService,
    as_user,
    make_venue,
    submit_body,
)
from fastapi.testclient import TestClient

from app import booking_decision_store
from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import booking_repository
from app.main import app
from app.slots import slots_to_range, touched_slots

client = TestClient(app)
AUTH = {"Authorization": "Bearer coordinator-token"}
DAY = "2030-01-10"


def hm(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def timed_body(venue_id: str, start: str, end: str, **overrides):
    body = submit_body(
        venue_id, start_minute=hm(start), end_minute=hm(end), **overrides
    )
    body.pop("slots", None)
    return body


@pytest.fixture
def events() -> FakeEventService:
    fake = FakeEventService()
    fake.add_event()
    as_user(COORDINATOR, "event_coordinator", events=fake)
    return fake


def stored_count() -> int:
    return sum(len(booking_repository.list_by_status(s)) for s in BookingRequestStatus)


def submit(body: dict):
    return client.post("/booking-requests", json=body, headers=AUTH)


def error_types(response) -> list[str]:
    return [error["type"] for error in response.json()["detail"]]


# AC1-H1 (happy): an assigned Coordinator submits a timed booking
def test_coordinator_submits_a_timed_booking(events: FakeEventService) -> None:
    venue = make_venue()

    response = submit(timed_body(venue.id, "10:00", "12:00"))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert (body["start_minute"], body["end_minute"]) == (600, 720)
    assert body["slots"] == ["AM"]
    stored = booking_repository.get(body["id"])
    assert (stored.start_minute, stored.end_minute) == (600, 720)


# AC1-B1 (boundary): the 07:00 and 24:00 window limits
@pytest.mark.parametrize(
    ("start", "end", "accepted"),
    [
        ("07:00", "08:00", True),
        ("23:45", "24:00", True),
        ("06:45", "08:00", False),
        ("23:00", "24:15", False),
    ],
)
def test_window_limits(events: FakeEventService, start: str, end: str, accepted: bool) -> None:
    venue = make_venue()

    response = submit(timed_body(venue.id, start, end))

    if accepted:
        assert response.status_code == 201
        assert stored_count() == 1
    else:
        assert response.status_code == 422
        assert "outside_operating_window" in error_types(response)
        assert stored_count() == 0


# AC1-B2 (boundary): the shortest booking is one 15-minute step
@pytest.mark.parametrize(
    ("start", "end", "accepted"),
    [("10:00", "10:15", True), ("10:00", "10:00", False), ("10:15", "10:00", False)],
)
def test_shortest_booking(events: FakeEventService, start: str, end: str, accepted: bool) -> None:
    venue = make_venue()

    response = submit(timed_body(venue.id, start, end))

    if accepted:
        assert response.status_code == 201
    else:
        assert response.status_code == 422
        assert "end_not_after_start" in error_types(response)
        assert stored_count() == 0


# AC1-N1 (negative): times off the 15-minute step are refused
@pytest.mark.parametrize(("start", "end"), [("10:10", "12:00"), ("10:00", "11:59")])
def test_off_step_is_refused(events: FakeEventService, start: str, end: str) -> None:
    venue = make_venue()

    response = submit(timed_body(venue.id, start, end))

    assert response.status_code == 422
    assert "off_step" in error_types(response)
    assert stored_count() == 0


# AC1-N2 (negative): the old slots field, or a missing time, is refused
@pytest.mark.parametrize(
    "body_change",
    [{"slots": ["AM"]}, {"end_minute": None}],
)
def test_old_or_missing_fields_are_refused(events: FakeEventService, body_change) -> None:
    venue = make_venue()
    body = timed_body(venue.id, "10:00", "12:00")
    for key, value in body_change.items():
        if value is None:
            body.pop(key)
        else:
            body[key] = value

    response = submit(body)

    assert response.status_code == 422
    assert stored_count() == 0


# AC1-P1 (partition): the slots a booking touches, during the transition
@pytest.mark.parametrize(
    ("start", "end", "slots"),
    [
        ("07:00", "12:00", ["AM"]),
        ("11:00", "13:00", ["AM", "PM"]),
        ("17:00", "19:00", ["PM", "NIGHT"]),
        ("07:00", "24:00", ["AM", "PM", "NIGHT"]),
    ],
)
def test_touched_slots(start: str, end: str, slots: list[str]) -> None:
    assert [s.value for s in touched_slots(hm(start), hm(end))] == slots


# AC5-H1 (happy): slot sets convert to the agreed ranges (stored model mirror)
@pytest.mark.parametrize(
    ("slots", "start", "end"),
    [
        (["AM"], "07:00", "12:00"),
        (["PM"], "12:00", "18:00"),
        (["NIGHT"], "18:00", "24:00"),
        (["PM", "AM"], "07:00", "18:00"),
        (["AM", "PM", "NIGHT"], "07:00", "24:00"),
    ],
)
def test_slots_convert_to_ranges(slots: list[str], start: str, end: str) -> None:
    assert slots_to_range(slots) == (hm(start), hm(end))
    booking = BookingRequest(
        venue_id="v", requested_by="u", event_request_id="e",
        start_date=date(2030, 1, 10), end_date=date(2030, 1, 10), slots=slots,
    )
    assert (booking.start_minute, booking.end_minute) == (hm(start), hm(end))


# AC5-N1 (negative): non-consecutive slots cannot become one range
def test_non_consecutive_slots_are_refused() -> None:
    with pytest.raises(ValueError, match="consecutive"):
        slots_to_range(["AM", "NIGHT"])


# --- AC2: approval compares bookings by time -------------------------------


@pytest.fixture
def staff():
    booking_decision_store.memory_decision_store.clear()
    yield
    booking_decision_store.memory_decision_store.clear()


def seed(venue_id: str, start: str, end: str, *, first=DAY, last=DAY, approved=False) -> str:
    booking = booking_repository.create(
        BookingRequest(
            venue_id=venue_id,
            requested_by=str(uuid4()),
            event_request_id=str(uuid4()),
            start_date=date.fromisoformat(first),
            end_date=date.fromisoformat(last),
            start_minute=hm(start),
            end_minute=hm(end),
        )
    )
    if approved:
        booking.status = BookingRequestStatus.APPROVED
    return booking.id


def approve(booking_id: str):
    return client.post(
        f"/booking-requests/{booking_id}/decision", json={"decision": "approved"}
    )


def status_of(booking_id: str) -> str:
    return booking_repository.get(booking_id).status.value


# AC2-H1 (happy): back-to-back bookings both approve (half-open ranges)
def test_back_to_back_bookings_both_approve(staff) -> None:
    venue = make_venue()
    seed(venue.id, "10:00", "12:00", approved=True)
    later = seed(venue.id, "12:00", "14:00")

    response = approve(later)

    assert response.status_code == 200
    assert status_of(later) == "approved"


# AC2-B1 (boundary): one step of overlap conflicts and records a refusal
def test_one_step_overlap_conflicts(staff) -> None:
    venue = make_venue()
    first = seed(venue.id, "10:00", "12:00", approved=True)
    later = seed(venue.id, "11:45", "14:00")

    response = approve(later)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["refusal_codes"] == ["booking_conflict"]
    assert detail["conflicting_booking_ids"] == [first]
    assert status_of(later) == "pending"
    refusals = client.get(f"/booking-requests/{later}/refusals").json()
    assert len(refusals) == 1


# AC2-P1 (partition): the same old slot without a time overlap no longer conflicts
def test_same_slot_without_time_overlap_approves(staff) -> None:
    venue = make_venue()
    seed(venue.id, "08:00", "10:00", approved=True)
    later = seed(venue.id, "10:00", "12:00")

    assert approve(later).status_code == 200


# AC2-P2 (partition): bookings conflict only when their dates share a day
def test_dates_must_share_a_day(staff) -> None:
    venue = make_venue()
    seed(venue.id, "10:00", "12:00", approved=True)
    next_day = seed(venue.id, "10:00", "12:00", first="2030-01-11", last="2030-01-11")
    spanning = seed(venue.id, "11:00", "13:00", first="2030-01-09", last="2030-01-10")

    assert approve(next_day).status_code == 200
    response = approve(spanning)
    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["booking_conflict"]


# AC2-X1 (cross-cutting): a PM block (12:00-18:00 since slice 2) refuses an overlapping time
def test_blocks_refuse_by_touched_slots(staff) -> None:
    venue = make_venue()
    block = client.post(
        f"/venues/{venue.id}/blocks",
        json={"start_date": DAY, "end_date": DAY, "start_minute": 720, "end_minute": 1080,
              "reason_category": "maintenance"},
    )
    assert block.status_code == 201
    crossing = seed(venue.id, "11:00", "13:00")
    morning = seed(venue.id, "08:00", "10:00")

    response = approve(crossing)
    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["active_block"]
    assert approve(morning).status_code == 200
