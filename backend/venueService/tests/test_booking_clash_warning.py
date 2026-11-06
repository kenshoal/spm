"""A clash warning when a booking request is submitted (SCRUM-67).

Every test carries its case ID from docs/testcases/scrum_67_testcases.md. The event
service is faked at the HTTP boundary, so the real client runs. The warning never blocks
a request: approval stays the hard check (SCRUM-20).
"""

from datetime import date

import pytest
from booking_support import (
    BASE_TIME,
    COORDINATOR,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    seed_booking,
    submit_body,
)
from fastapi.testclient import TestClient

from app.booking_models import BookingRequestStatus
from app.booking_repository import booking_repository
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer coordinator-token"}
DAY = date(2030, 1, 10)


@pytest.fixture
def events() -> FakeEventService:
    fake = FakeEventService()
    fake.add_event()
    as_user(COORDINATOR, "event_coordinator", events=fake)
    return fake


def approved(venue_id: str, start_minute: int = 540, end_minute: int = 720, start: date = DAY, end: date = DAY, **extra):
    return seed_booking(
        venue_id=venue_id,
        start_date=start,
        end_date=end,
        start_minute=start_minute,
        end_minute=end_minute,
        status=BookingRequestStatus.APPROVED,
        decided_by=STAFF,
        decided_at=BASE_TIME,
        event_request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        **extra,
    )


def submit(venue_id: str, start_minute: int, end_minute: int, **overrides):
    body = submit_body(venue_id, start_minute=start_minute, end_minute=end_minute, **overrides)
    return client.post("/booking-requests", json=body, headers=AUTH)


# AC1-H1 (happy): a request that overlaps an approved booking is stored and lists the clash
def test_a_clashing_request_is_stored_and_names_the_clash(events: FakeEventService) -> None:
    venue = make_venue()
    approved(venue.id, 540, 720)

    response = submit(venue.id, 600, 660)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["conflicts"] == [
        {"start_date": "2030-01-10", "end_date": "2030-01-10", "start_minute": 540, "end_minute": 720}
    ]
    assert booking_repository.get(body["id"]) is not None


# AC1-P1 (partition): a request with no clash lists none
def test_a_free_time_lists_no_clash(events: FakeEventService) -> None:
    venue = make_venue()
    approved(venue.id, 540, 720)

    response = submit(venue.id, 900, 960)

    assert response.status_code == 201
    assert response.json()["conflicts"] == []


# AC1-P2 (partition): bookings that do not hold the venue at that time do not count
@pytest.mark.parametrize(
    "other",
    [
        {"status": BookingRequestStatus.PENDING},
        {"status": BookingRequestStatus.REJECTED, "decision_reason": "No", "decided_by": STAFF, "decided_at": BASE_TIME},
        {"status": BookingRequestStatus.CANCELLED, "cancelled_by": COORDINATOR, "cancelled_at": BASE_TIME},
    ],
    ids=["pending", "rejected", "cancelled"],
)
def test_bookings_that_do_not_hold_the_venue_do_not_count(events: FakeEventService, other: dict) -> None:
    venue = make_venue()
    seed_booking(venue_id=venue.id, start_date=DAY, end_date=DAY, start_minute=540, end_minute=720, **other)

    assert submit(venue.id, 600, 660).json()["conflicts"] == []


# AC1-P3 (partition): another venue's approved booking and another date do not count
def test_another_venue_or_date_does_not_count(events: FakeEventService) -> None:
    venue, elsewhere = make_venue(name="This Hall"), make_venue(name="Other Hall")
    approved(elsewhere.id, 540, 720)
    approved(venue.id, 540, 720, start=date(2030, 1, 12), end=date(2030, 1, 12))

    assert submit(venue.id, 600, 660).json()["conflicts"] == []


# AC1-P4 (partition): a multi-day approved booking clashes on any shared date
def test_a_multi_day_booking_clashes_on_a_shared_date(events: FakeEventService) -> None:
    venue = make_venue()
    approved(venue.id, 540, 720, start=date(2030, 1, 9), end=date(2030, 1, 11))

    response = submit(venue.id, 600, 660)

    assert response.json()["conflicts"] == [
        {"start_date": "2030-01-09", "end_date": "2030-01-11", "start_minute": 540, "end_minute": 720}
    ]


# AC1-B1, AC1-B2, AC1-B3 (boundary): setup and turnaround count. With setup 30 and turnaround 45
# an approved 09:00-12:00 booking holds the venue 08:30-12:45, so a request needs 30 minutes of
# setup after that: 13:15 is the earliest clear start.
@pytest.mark.parametrize(
    ("start_minute", "clashes"),
    [(780, True), (795, False), (810, False)],
    ids=["AC1-B1-just-inside", "AC1-B2-exactly-clear", "AC1-B3-after"],
)
def test_setup_and_turnaround_are_counted(events: FakeEventService, start_minute: int, clashes: bool) -> None:
    venue = make_venue(setup_minutes=30, turnaround_minutes=45)
    approved(venue.id, 540, 720)

    response = submit(venue.id, start_minute, start_minute + 60)

    assert response.status_code == 201
    assert bool(response.json()["conflicts"]) is clashes


# AC1-B4 (boundary): the near edge. With setup 30 and turnaround 45 the approved 09:00-12:00
# booking holds the venue from 08:30, so a request 07:30-07:45 pads to end exactly at 08:30 and
# is clear (ranges are half-open); one step more pads to 08:45 and clashes.
@pytest.mark.parametrize(
    ("end_minute", "clashes"),
    [(465, False), (480, True)],
    ids=["AC1-B4-touching-clear", "AC1-B4-one-step-more-clashes"],
)
def test_a_touching_padded_end_is_clear_but_one_step_more_clashes(
    events: FakeEventService, end_minute: int, clashes: bool
) -> None:
    venue = make_venue(setup_minutes=30, turnaround_minutes=45)
    approved(venue.id, 540, 720)

    response = submit(venue.id, 450, end_minute)

    assert response.status_code == 201
    assert bool(response.json()["conflicts"]) is clashes


# AC1-X1 (cross-cutting): the warning carries times and dates only, never event names, ids or users
def test_the_warning_hides_other_events_details(events: FakeEventService) -> None:
    venue = make_venue()
    other = approved(venue.id, 540, 720, event_name="Hidden Gala", requested_by="66666666-6666-4666-8666-666666666666")

    response = submit(venue.id, 600, 660)

    for secret in ("Hidden Gala", other.id, other.requested_by, other.event_request_id):
        assert secret not in response.text
    assert set(response.json()["conflicts"][0]) == {"start_date", "end_date", "start_minute", "end_minute"}


# AC2-H1 (happy): a clash never blocks the request and changes no other booking
def test_a_clash_does_not_change_the_clashing_booking(events: FakeEventService) -> None:
    venue = make_venue()
    other = approved(venue.id, 540, 720)
    before = other.model_dump(mode="json")

    assert submit(venue.id, 600, 660).status_code == 201

    assert booking_repository.get(other.id).model_dump(mode="json") == before
    assert len(booking_repository.list_for_event(submit_body(venue.id)["event_request_id"])) == 1


# AC2-X1 (cross-cutting): approval stays the hard check, so the clashing request is refused there
def test_approval_still_refuses_the_clashing_request(events: FakeEventService) -> None:
    venue = make_venue()
    approved(venue.id, 540, 720)
    created = submit(venue.id, 600, 660).json()
    as_user(STAFF, "venue_staff", events=events)

    response = client.post(f"/booking-requests/{created['id']}/decision", json={"decision": "approved"})

    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["booking_conflict"]
    assert booking_repository.get(created["id"]).status is BookingRequestStatus.PENDING


# AC1-N1 (negative): if the clash lookup fails the request is still stored, with no warning
def test_a_failed_lookup_does_not_fail_the_request(events: FakeEventService, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.supabase_repository import SupabaseRepositoryError

    venue = make_venue()

    def fail(*_args, **_kwargs):
        raise SupabaseRepositoryError("down")

    monkeypatch.setattr(booking_repository, "list_approved_for_venue", fail)

    response = submit(venue.id, 600, 660)

    assert response.status_code == 201
    assert response.json()["conflicts"] == []
    assert booking_repository.get(response.json()["id"]) is not None
