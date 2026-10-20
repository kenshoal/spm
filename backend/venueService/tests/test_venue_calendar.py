"""Venue availability calendar (SCRUM-31).

Every test carries its case ID from docs/testcases/scrum_31_testcases.md.
"""

from datetime import date

import pytest
from booking_support import (
    BASE_TIME,
    COORDINATOR,
    ORGANISER,
    STAFF,
    as_user,
    make_venue,
    seed_booking,
)
from fastapi.testclient import TestClient

from app.block_models import BlockReason, BlockStatus, VenueBlockCreate
from app.block_repository import block_repository
from app.booking_models import BookingRequestStatus
from app.dependencies import require_authenticated, require_venue_staff
from app.main import app
from app.repository import repository

client = TestClient(app)
SAFETY_OFFICER = "55555555-5555-4555-8555-555555555555"
OTHER = "66666666-6666-4666-8666-666666666666"


@pytest.fixture(autouse=True)
def _coordinator() -> None:
    as_user(COORDINATOR, "event_coordinator")
    yield
    app.dependency_overrides.pop(require_venue_staff, None)


def calendar(venue_id: str, month: str = "2026-10"):
    return client.get(f"/venues/{venue_id}/calendar", params={"month": month})


def states(body: dict, day: str) -> dict[str, str]:
    entry = next(item for item in body["days"] if item["date"] == day)
    return {cell["slot"]: cell["state"] for cell in entry["slots"]}


def block(venue_id: str, start: str, end: str, slots: list[str], **extra):
    created = block_repository.create(
        venue_id,
        VenueBlockCreate(
            start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end),
            slots=slots,
            reason_category=BlockReason.MAINTENANCE,
            reason_detail=extra.pop("detail", "Air-con repairs"),
        ),
        created_by=STAFF,
    )
    if extra.get("status"):
        created.status = extra["status"]
    return created


def approved(venue_id: str, start: str, end: str, slots: list[str], **extra):
    return seed_booking(
        venue_id=venue_id,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        slots=slots,
        status=BookingRequestStatus.APPROVED,
        decided_by=STAFF,
        decided_at=BASE_TIME,
        **extra,
    )


# AC1-H1 (happy): a coordinator reads a month for an open venue
def test_coordinator_reads_a_month_for_an_open_venue() -> None:
    venue = make_venue()

    response = calendar(venue.id)

    assert response.status_code == 200
    body = response.json()
    assert body["venue_id"] == venue.id
    assert body["month"] == "2026-10"
    assert body["days"][0]["date"] == "2026-10-01"
    assert len(body["days"]) == 31
    for day in body["days"]:
        assert [cell["slot"] for cell in day["slots"]] == ["AM", "PM", "NIGHT"]
        assert all(cell["state"] == "open" for cell in day["slots"])


# AC1-P1, AC1-P2 (partition): venue staff and a safety officer may also read it
@pytest.mark.parametrize(
    ("user_id", "role"),
    [(STAFF, "venue_staff"), (SAFETY_OFFICER, "safety_officer")],
    ids=["AC1-P1", "AC1-P2"],
)
def test_other_allowed_roles_can_read_the_calendar(user_id: str, role: str) -> None:
    venue = make_venue()
    as_user(user_id, role)

    response = calendar(venue.id)

    assert response.status_code == 200
    assert len(response.json()["days"]) == 31


# AC1-B1, AC1-B2, AC1-B3 (boundary): month lengths, leap year and year end
@pytest.mark.parametrize(
    ("month", "count", "last"),
    [("2028-02", 29, "2028-02-29"), ("2027-02", 28, "2027-02-28"), ("2026-12", 31, "2026-12-31")],
    ids=["AC1-B1", "AC1-B2", "AC1-B3"],
)
def test_month_lengths(month: str, count: int, last: str) -> None:
    venue = make_venue()

    days = calendar(venue.id, month).json()["days"]

    assert len(days) == count
    assert days[-1]["date"] == last


# AC1-N1 to AC1-N6 (negative): a month that is not YYYY-MM is refused
@pytest.mark.parametrize(
    "month",
    ["2026-13", "2026-00", "2026-1", "26-10", "abc", None],
    ids=["AC1-N1", "AC1-N2", "AC1-N3", "AC1-N4", "AC1-N5", "AC1-N6"],
)
def test_invalid_month_is_refused(month: str | None) -> None:
    venue = make_venue()
    params = {} if month is None else {"month": month}

    response = client.get(f"/venues/{venue.id}/calendar", params=params)

    assert response.status_code == 422


# AC1-N7 (negative): an unknown venue returns 404
def test_unknown_venue_returns_404() -> None:
    response = calendar("does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}


# AC1-N8, AC1-N9, AC1-N10 (negative): other roles are refused (A2)
@pytest.mark.parametrize(
    "role",
    ["event_organiser", "attendee", "technical_support"],
    ids=["AC1-N8", "AC1-N9", "AC1-N10"],
)
def test_other_roles_are_refused(role: str) -> None:
    venue = make_venue()
    as_user(ORGANISER, role)

    response = calendar(venue.id)

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


# AC1-X1 (cross-cutting): a request without a token is refused
def test_calendar_requires_authentication() -> None:
    venue = make_venue()
    app.dependency_overrides.pop(require_authenticated, None)
    app.dependency_overrides.pop(require_venue_staff, None)

    response = calendar(venue.id)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


# AC1-X2 (cross-cutting): the response carries no private details (A3)
@pytest.mark.parametrize(
    ("user_id", "role"),
    [(COORDINATOR, "event_coordinator"), (STAFF, "venue_staff"), (SAFETY_OFFICER, "safety_officer")],
    ids=["coordinator", "staff", "safety-officer"],
)
def test_response_has_no_private_details(user_id: str, role: str) -> None:
    venue = make_venue()
    secret_block = block(venue.id, "2026-10-20", "2026-10-21", ["NIGHT"], detail="Hidden-roof-leak")
    booking = approved(venue.id, "2026-10-12", "2026-10-14", ["AM"], event_name="Hidden Gala", requested_by=OTHER)
    as_user(user_id, role)

    text = calendar(venue.id).text

    for secret in ("Hidden-roof-leak", "maintenance", "Hidden Gala", secret_block.id, booking.id, OTHER, STAFF):
        assert secret not in text
    assert set(calendar(venue.id).json()) == {"venue_id", "month", "days"}


# AC2-H1 (happy): an approved booking shows as booked on its dates and slots only
def test_approved_booking_shows_as_booked() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-14", ["AM", "PM"])

    body = calendar(venue.id).json()

    for day in ("2026-10-12", "2026-10-13", "2026-10-14"):
        assert states(body, day) == {"AM": "booked", "PM": "booked", "NIGHT": "open"}
    assert states(body, "2026-10-11") == {"AM": "open", "PM": "open", "NIGHT": "open"}


# AC2-B1, AC2-B2 (boundary): the first and last date are included, the days around are not
@pytest.mark.parametrize(
    ("day", "expected"),
    [("2026-10-11", "open"), ("2026-10-12", "booked"), ("2026-10-14", "booked"), ("2026-10-15", "open")],
    ids=["AC2-B1-before", "AC2-B1-first", "AC2-B2-last", "AC2-B2-after"],
)
def test_booking_boundaries_are_inclusive(day: str, expected: str) -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-14", ["AM"])

    assert states(calendar(venue.id).json(), day)["AM"] == expected


# AC2-H2 (happy): an active block shows as blocked on its dates and slots
def test_active_block_shows_as_blocked() -> None:
    venue = make_venue()
    block(venue.id, "2026-10-20", "2026-10-21", ["NIGHT"])

    body = calendar(venue.id).json()

    assert states(body, "2026-10-20")["NIGHT"] == "blocked"
    assert states(body, "2026-10-21")["NIGHT"] == "blocked"
    assert states(body, "2026-10-20")["AM"] == "open"
    assert states(body, "2026-10-22")["NIGHT"] == "open"


# AC2-P1 (partition): a lifted block does not show
def test_lifted_block_does_not_show() -> None:
    venue = make_venue()
    block(venue.id, "2026-10-20", "2026-10-21", ["NIGHT"], status=BlockStatus.LIFTED)

    assert states(calendar(venue.id).json(), "2026-10-20")["NIGHT"] == "open"


# AC2-P2, AC2-P3, AC2-P4 (partition): pending, rejected and cancelled bookings do not show as booked
@pytest.mark.parametrize(
    "extra",
    [
        {"status": BookingRequestStatus.PENDING},
        {"status": BookingRequestStatus.REJECTED, "decision_reason": "No", "decided_by": STAFF, "decided_at": BASE_TIME},
        {"status": BookingRequestStatus.CANCELLED, "cancelled_by": COORDINATOR, "cancelled_at": BASE_TIME},
    ],
    ids=["AC2-P2", "AC2-P3", "AC2-P4"],
)
def test_only_approved_bookings_show_as_booked(extra: dict) -> None:
    venue = make_venue()
    seed_booking(
        venue_id=venue.id,
        start_date=date(2026, 10, 12),
        end_date=date(2026, 10, 12),
        slots=["AM"],
        **extra,
    )

    assert states(calendar(venue.id).json(), "2026-10-12")["AM"] == "open"


# AC2-P5 (partition): a multi-day, multi-slot booking covers every slot of every day
def test_multi_day_multi_slot_booking_covers_every_cell() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-05", "2026-10-07", ["AM", "PM"])

    days = calendar(venue.id).json()["days"]

    booked = [
        (day["date"], cell["slot"])
        for day in days
        for cell in day["slots"]
        if cell["state"] == "booked"
    ]
    assert len(booked) == 6
    assert {slot for _date, slot in booked} == {"AM", "PM"}


# AC2-X1 (cross-cutting): a booking spanning two months shows in both; one outside does not
def test_booking_spanning_two_months_shows_in_both() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-30", "2026-11-02", ["AM"])
    approved(venue.id, "2026-12-10", "2026-12-10", ["AM"])

    october = calendar(venue.id, "2026-10").json()
    november = calendar(venue.id, "2026-11").json()

    assert states(october, "2026-10-30")["AM"] == "booked"
    assert states(october, "2026-10-31")["AM"] == "booked"
    assert states(november, "2026-11-01")["AM"] == "booked"
    assert states(november, "2026-11-02")["AM"] == "booked"
    assert states(november, "2026-11-03")["AM"] == "open"
    for body in (october, november):
        assert all(cell["state"] != "booked" or day["date"] in {"2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"}
                   for day in body["days"] for cell in day["slots"])


# AC2-X2 (cross-cutting): reading changes nothing
def test_reading_changes_nothing() -> None:
    venue = make_venue()
    block(venue.id, "2026-10-20", "2026-10-21", ["NIGHT"])
    approved(venue.id, "2026-10-12", "2026-10-14", ["AM"])

    def snapshot():
        from app.booking_repository import booking_repository

        return (
            repository.get(venue.id).model_dump(mode="json"),
            [item.model_dump(mode="json") for item in block_repository.list_for_venue(venue.id)],
            [item.model_dump(mode="json") for item in booking_repository.list_by_status("approved")],
        )

    before = snapshot()
    assert calendar(venue.id).status_code == 200
    assert calendar(venue.id).status_code == 200

    assert snapshot() == before


# AC3-H1 (happy): a slot that is both booked and blocked shows as blocked
def test_blocked_wins_over_booked() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-12", ["AM"])
    block(venue.id, "2026-10-12", "2026-10-12", ["AM"])

    assert states(calendar(venue.id).json(), "2026-10-12")["AM"] == "blocked"


# AC3-H2 (happy): cancelling an approved booking makes its slots open again
def test_cancelled_booking_frees_its_slots() -> None:
    venue = make_venue()
    booking = approved(venue.id, "2026-10-12", "2026-10-12", ["AM"])
    assert states(calendar(venue.id).json(), "2026-10-12")["AM"] == "booked"

    booking.status = BookingRequestStatus.CANCELLED
    booking.cancelled_by = COORDINATOR
    booking.cancelled_at = BASE_TIME

    assert states(calendar(venue.id).json(), "2026-10-12")["AM"] == "open"


# AC3-X1 (cross-cutting): the calendar and venue search agree for every date and slot
def test_calendar_agrees_with_venue_search() -> None:
    plain = make_venue(name="Plain Hall")
    busy = make_venue(name="Busy Hall")
    am_only = make_venue(name="Morning Hall", operating_slots=["AM"])
    closed = make_venue(name="Closed Hall", status="blocked")
    approved(busy.id, "2026-10-03", "2026-10-04", ["AM", "PM"])
    block(busy.id, "2026-10-06", "2026-10-06", ["NIGHT"])
    block(plain.id, "2026-10-07", "2026-10-08", ["PM"])
    venues = [plain, busy, am_only, closed]

    for venue in venues:
        body = calendar(venue.id).json()
        for day in range(1, 11):
            date_text = f"2026-10-{day:02d}"
            for slot in ("AM", "PM", "NIGHT"):
                found = client.get(
                    "/venues/search", params={"date": date_text, "slot": slot}
                ).json()
                in_search = venue.id in [item["id"] for item in found]
                is_open = states(body, date_text)[slot] == "open"
                assert in_search == is_open, (venue.name, date_text, slot)


# AC4-P1 (partition): a slot the venue does not operate shows as not offered
def test_non_operating_slot_is_not_offered() -> None:
    venue = make_venue(operating_slots=["AM", "PM"])

    body = calendar(venue.id).json()

    assert all(states(body, day["date"])["NIGHT"] == "not_offered" for day in body["days"])
    assert states(body, "2026-10-05")["AM"] == "open"


# AC4-P2 (partition): a venue blocked in the catalogue shows its operating slots as unavailable
def test_catalogue_blocked_venue_is_unavailable() -> None:
    venue = make_venue(operating_slots=["AM", "PM"], status="blocked")

    assert states(calendar(venue.id).json(), "2026-10-05") == {
        "AM": "unavailable",
        "PM": "unavailable",
        "NIGHT": "not_offered",
    }


# AC4-P3 (partition): an active block on a slot the venue does not operate still shows (A6)
def test_block_on_non_operating_slot_still_shows() -> None:
    venue = make_venue(operating_slots=["AM"])
    block(venue.id, "2026-10-20", "2026-10-20", ["NIGHT"])

    assert states(calendar(venue.id).json(), "2026-10-20")["NIGHT"] == "blocked"
