"""Venue availability calendar on times (SCRUM-31, moved to times by SCRUM-69).

Every test carries its case ID from docs/testcases/scrum_69_testcases.md.
Times are minutes after midnight: 09:00 = 540, 12:00 = 720, 24:00 = 1440.
"""

from datetime import date
from itertools import pairwise

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
from app.calendar_view import build_calendar
from app.dependencies import require_authenticated, require_venue_staff
from app.main import app
from app.repository import repository

client = TestClient(app)
SAFETY_OFFICER = "55555555-5555-4555-8555-555555555555"
OTHER = "66666666-6666-4666-8666-666666666666"
OPEN, CLOSE = 420, 1440
FULL_DAY = [{"start_minute": OPEN, "end_minute": CLOSE}]


@pytest.fixture(autouse=True)
def _coordinator() -> None:
    as_user(COORDINATOR, "event_coordinator")
    yield
    app.dependency_overrides.pop(require_venue_staff, None)


def calendar(venue_id: str, month: str = "2026-10"):
    return client.get(f"/venues/{venue_id}/calendar", params={"month": month})


def day(body: dict, text: str) -> dict:
    return next(item for item in body["days"] if item["date"] == text)


def entries(body: dict, text: str) -> list[tuple[str, int, int]]:
    return [
        (e["state"], e["start_minute"], e["end_minute"]) for e in day(body, text)["entries"]
    ]


def free(body: dict, text: str) -> list[tuple[int, int]]:
    return [(r["start_minute"], r["end_minute"]) for r in day(body, text)["free"]]


def block(venue_id: str, start: str, end: str, start_minute: int, end_minute: int, **extra):
    created = block_repository.create(
        venue_id,
        VenueBlockCreate(
            start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end),
            start_minute=start_minute,
            end_minute=end_minute,
            reason_category=BlockReason.MAINTENANCE,
            reason_detail=extra.pop("detail", "Air-con repairs"),
        ),
        created_by=STAFF,
    )
    if extra.get("status"):
        created.status = extra["status"]
    return created


def approved(venue_id: str, start: str, end: str, start_minute: int, end_minute: int, **extra):
    return seed_booking(
        venue_id=venue_id,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        start_minute=start_minute,
        end_minute=end_minute,
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
    for item in body["days"]:
        assert item["unavailable"] is False
        assert item["entries"] == []
        assert item["free"] == FULL_DAY


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


# AC1-N1 to AC1-N6, AC1-N11 (negative): a month that is not a real YYYY-MM is refused (including year 0000)
@pytest.mark.parametrize(
    "month",
    ["2026-13", "2026-00", "2026-1", "26-10", "abc", None, "0000-01"],
    ids=["AC1-N1", "AC1-N2", "AC1-N3", "AC1-N4", "AC1-N5", "AC1-N6", "AC1-N11"],
)
def test_invalid_month_is_refused(month: str | None) -> None:
    venue = make_venue()
    params = {} if month is None else {"month": month}

    response = client.get(f"/venues/{venue.id}/calendar", params=params)

    assert response.status_code == 422


# AC1-B4, AC1-B5 (boundary): the first and last month the calendar can show both work
@pytest.mark.parametrize("month", ["0001-01", "9999-12"], ids=["AC1-B4", "AC1-B5"])
def test_first_and_last_representable_months(month: str) -> None:
    venue = make_venue()

    response = calendar(venue.id, month)

    assert response.status_code == 200
    assert len(response.json()["days"]) == 31


# AC1-N7 (negative): an unknown venue returns 404
def test_unknown_venue_returns_404() -> None:
    response = calendar("does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}


# AC1-N8, AC1-N9, AC1-N10 (negative): other roles are refused
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


# AC1-X2 (cross-cutting): every date is an ordered, gap-free, non-overlapping partition of 07:00-24:00
def test_every_date_partitions_the_operating_window() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-05", "2026-10-07", 540, 720)
    approved(venue.id, "2026-10-05", "2026-10-05", 600, 840)
    approved(venue.id, "2026-10-06", "2026-10-06", 720, 780)
    block(venue.id, "2026-10-05", "2026-10-06", 660, 900)
    block(venue.id, "2026-10-07", "2026-10-07", 420, 480)
    block(venue.id, "2026-10-07", "2026-10-07", 1380, 1440)

    for item in calendar(venue.id).json()["days"]:
        ranges = sorted(
            [(e["start_minute"], e["end_minute"]) for e in item["entries"]]
            + [(r["start_minute"], r["end_minute"]) for r in item["free"]]
        )
        assert ranges[0][0] == OPEN, item["date"]
        assert ranges[-1][1] == CLOSE, item["date"]
        for (start, end), (next_start, _next_end) in pairwise(ranges):
            assert start < end and end == next_start, item["date"]
        assert all(start % 15 == 0 and end % 15 == 0 for start, end in ranges)


# AC2-H1 (happy): an approved booking shows its times on each of its dates only
def test_approved_booking_shows_as_booked() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-14", 540, 720)

    body = calendar(venue.id).json()

    for text in ("2026-10-12", "2026-10-13", "2026-10-14"):
        assert entries(body, text) == [("booked", 540, 720)]
        assert free(body, text) == [(420, 540), (720, 1440)]
    for text in ("2026-10-11", "2026-10-15"):
        assert entries(body, text) == []
        assert free(body, text) == [(420, 1440)]


# AC2-B1, AC2-B2 (boundary): the first and last date are included, the days around are not
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-11", []),
        ("2026-10-12", [("booked", 540, 720)]),
        ("2026-10-14", [("booked", 540, 720)]),
        ("2026-10-15", []),
    ],
    ids=["AC2-B1-before", "AC2-B1-first", "AC2-B2-last", "AC2-B2-after"],
)
def test_booking_date_boundaries_are_inclusive(text: str, expected: list) -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-14", 540, 720)

    assert entries(calendar(venue.id).json(), text) == expected


# AC2-B3, AC2-B4 (boundary): a booking at the window edges and a one-step booking
def test_edge_and_one_step_bookings() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-12", 420, 435)
    approved(venue.id, "2026-10-13", "2026-10-13", 1425, 1440)
    approved(venue.id, "2026-10-14", "2026-10-14", 720, 735)

    body = calendar(venue.id).json()

    assert entries(body, "2026-10-12") == [("booked", 420, 435)]
    assert free(body, "2026-10-12") == [(435, 1440)]
    assert entries(body, "2026-10-13") == [("booked", 1425, 1440)]
    assert free(body, "2026-10-13") == [(420, 1425)]
    assert entries(body, "2026-10-14") == [("booked", 720, 735)]
    assert free(body, "2026-10-14") == [(420, 720), (735, 1440)]


# AC2-B5 (boundary): ranges are half-open, so a booking ending at 12:00 leaves 12:00 free
def test_a_booking_ending_at_noon_leaves_noon_free() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-12", 540, 720)

    body = calendar(venue.id).json()

    assert (720, 1440) in free(body, "2026-10-12")
    assert all(start != 719 for start, _end in free(body, "2026-10-12"))


# AC2-H2 (happy): an active block shows its times on its dates
def test_active_block_shows_as_blocked() -> None:
    venue = make_venue()
    block(venue.id, "2026-10-20", "2026-10-21", 1080, 1440)

    body = calendar(venue.id).json()

    for text in ("2026-10-20", "2026-10-21"):
        assert entries(body, text) == [("blocked", 1080, 1440)]
        assert free(body, text) == [(420, 1080)]
    assert entries(body, "2026-10-22") == []
    assert free(body, "2026-10-22") == [(420, 1440)]


# AC2-P1 (partition): a lifted block does not show
def test_lifted_block_does_not_show() -> None:
    venue = make_venue()
    block(venue.id, "2026-10-20", "2026-10-21", 1080, 1440, status=BlockStatus.LIFTED)

    assert entries(calendar(venue.id).json(), "2026-10-20") == []


# AC2-P2, AC2-P3, AC2-P4 (partition): pending, rejected and cancelled bookings do not show
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
        start_minute=540,
        end_minute=720,
        **extra,
    )

    body = calendar(venue.id).json()

    assert entries(body, "2026-10-12") == []
    assert free(body, "2026-10-12") == [(420, 1440)]


# AC2-P5 (partition): a multi-day booking applies its times to every date
def test_multi_day_booking_applies_its_times_to_every_date() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-05", "2026-10-07", 540, 720)

    days = calendar(venue.id).json()["days"]

    booked = [item["date"] for item in days if item["entries"]]
    assert booked == ["2026-10-05", "2026-10-06", "2026-10-07"]
    assert all(
        [(e["start_minute"], e["end_minute"]) for e in item["entries"]] == [(540, 720)]
        for item in days
        if item["entries"]
    )


# AC2-H3 (happy): where a block and a booking overlap the time is blocked and the booking is split
def test_blocked_wins_over_booked_and_splits_the_booking() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-12", 540, 720)
    block(venue.id, "2026-10-12", "2026-10-12", 600, 660)

    body = calendar(venue.id).json()

    assert entries(body, "2026-10-12") == [
        ("booked", 540, 600),
        ("blocked", 600, 660),
        ("booked", 660, 720),
    ]
    assert free(body, "2026-10-12") == [(420, 540), (720, 1440)]


# AC2-H4 (happy): two touching bookings are one booked range, so no boundary between events shows
def test_touching_bookings_are_one_booked_range() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-12", "2026-10-12", 540, 600)
    approved(venue.id, "2026-10-12", "2026-10-12", 600, 660)

    assert entries(calendar(venue.id).json(), "2026-10-12") == [("booked", 540, 660)]


# AC2-H5 (happy): cancelling an approved booking frees its time
def test_cancelled_booking_frees_its_time() -> None:
    venue = make_venue()
    booking = approved(venue.id, "2026-10-12", "2026-10-12", 540, 720)
    assert entries(calendar(venue.id).json(), "2026-10-12") == [("booked", 540, 720)]

    booking.status = BookingRequestStatus.CANCELLED
    booking.cancelled_by = COORDINATOR
    booking.cancelled_at = BASE_TIME

    body = calendar(venue.id).json()
    assert entries(body, "2026-10-12") == []
    assert free(body, "2026-10-12") == [(420, 1440)]


# AC2-X1 (cross-cutting): a booking spanning two months shows in both; one outside does not
def test_booking_spanning_two_months_shows_in_both() -> None:
    venue = make_venue()
    approved(venue.id, "2026-10-30", "2026-11-02", 540, 720)
    approved(venue.id, "2026-12-10", "2026-12-10", 540, 720)

    october = calendar(venue.id, "2026-10").json()
    november = calendar(venue.id, "2026-11").json()

    assert [i["date"] for i in october["days"] if i["entries"]] == ["2026-10-30", "2026-10-31"]
    assert [i["date"] for i in november["days"] if i["entries"]] == ["2026-11-01", "2026-11-02"]


# AC2-X2 (cross-cutting): reading changes nothing
def test_reading_changes_nothing() -> None:
    venue = make_venue()
    block(venue.id, "2026-10-20", "2026-10-21", 1080, 1440)
    approved(venue.id, "2026-10-12", "2026-10-14", 540, 720)

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


# AC3-P1, AC3-P2 (partition): a venue blocked in the catalogue shows its dates unavailable
@pytest.mark.parametrize(
    ("status", "unavailable"),
    [("blocked", True), ("available", False)],
    ids=["AC3-P1", "AC3-P2"],
)
def test_catalogue_status_sets_the_unavailable_flag(status: str, unavailable: bool) -> None:
    venue = make_venue(status=status)

    days = calendar(venue.id).json()["days"]

    assert all(item["unavailable"] is unavailable for item in days)
    assert all((item["free"] == []) is unavailable for item in days)


# AC3-P3 (partition): a block on a catalogue-blocked venue still shows
def test_block_on_an_unavailable_venue_still_shows() -> None:
    venue = make_venue(status="blocked")
    block(venue.id, "2026-10-20", "2026-10-20", 1080, 1440)

    item = day(calendar(venue.id).json(), "2026-10-20")

    assert item["unavailable"] is True
    assert [(e["state"], e["start_minute"], e["end_minute"]) for e in item["entries"]] == [
        ("blocked", 1080, 1440)
    ]


# AC4-X1 (cross-cutting): the response carries no private details and only the agreed fields
@pytest.mark.parametrize(
    ("user_id", "role"),
    [(COORDINATOR, "event_coordinator"), (STAFF, "venue_staff"), (SAFETY_OFFICER, "safety_officer")],
    ids=["coordinator", "staff", "safety-officer"],
)
def test_response_has_no_private_details(user_id: str, role: str) -> None:
    venue = make_venue()
    secret_block = block(venue.id, "2026-10-20", "2026-10-21", 1080, 1440, detail="Hidden-roof-leak")
    booking = approved(venue.id, "2026-10-12", "2026-10-14", 540, 720, event_name="Hidden Gala", requested_by=OTHER)
    as_user(user_id, role)

    response = calendar(venue.id)
    body = response.json()

    for secret in ("Hidden-roof-leak", "maintenance", "Hidden Gala", secret_block.id, booking.id, OTHER, STAFF):
        assert secret not in response.text
    assert set(body) == {"venue_id", "month", "days"}
    for item in body["days"]:
        assert set(item) == {"date", "unavailable", "entries", "free"}
        assert all(set(e) == {"state", "start_minute", "end_minute"} for e in item["entries"])
        assert all(set(r) == {"start_minute", "end_minute"} for r in item["free"])


# AC5-X1 (cross-cutting): no slot vocabulary in the response
def test_response_has_no_slot_vocabulary() -> None:
    venue = make_venue(operating_slots=["AM", "PM"])
    approved(venue.id, "2026-10-12", "2026-10-12", 540, 720)
    block(venue.id, "2026-10-13", "2026-10-13", 1080, 1440)

    text = calendar(venue.id).text

    for word in ("slot", "AM", "PM", "NIGHT", "not_offered", "operating_slots"):
        assert word not in text, word


# AC6-X1 (cross-cutting): the calendar and venue search agree at every 15-minute step
def test_calendar_agrees_with_venue_search_at_every_step() -> None:
    plain = make_venue(name="Plain Hall")
    busy = make_venue(name="Busy Hall")
    closed = make_venue(name="Closed Hall", status="blocked")
    approved(busy.id, "2026-10-03", "2026-10-04", 540, 735)
    block(busy.id, "2026-10-04", "2026-10-04", 600, 660)
    block(busy.id, "2026-10-06", "2026-10-06", 1380, 1440)
    block(plain.id, "2026-10-07", "2026-10-07", 420, 435)

    for venue in (plain, busy, closed):
        body = calendar(venue.id).json()
        for number in (3, 4, 5, 6, 7):
            text = f"2026-10-{number:02d}"
            item = day(body, text)
            for start in range(OPEN, CLOSE, 15):
                found = client.get(
                    "/venues/search",
                    params={"date": text, "start_minute": start, "end_minute": start + 15},
                ).json()
                in_search = venue.id in [v["id"] for v in found]
                is_free = not item["unavailable"] and any(
                    r["start_minute"] <= start and start + 15 <= r["end_minute"] for r in item["free"]
                )
                assert in_search == is_free, (venue.name, text, start)


# AC2-P6 (partition): build_calendar itself ignores bookings that are not approved, whatever it is handed
@pytest.mark.parametrize(
    "status",
    [BookingRequestStatus.PENDING, BookingRequestStatus.REJECTED, BookingRequestStatus.CANCELLED],
    ids=["pending", "rejected", "cancelled"],
)
def test_build_calendar_ignores_bookings_that_are_not_approved(status: BookingRequestStatus) -> None:
    venue = make_venue()
    held = approved(venue.id, "2026-10-12", "2026-10-12", 540, 720)
    held.status = status

    built = build_calendar(venue, "2026-10", [], [held])

    assert built.days[11].entries == []


# AC2-P7 (partition): build_calendar itself ignores another venue's blocks and bookings
def test_build_calendar_ignores_other_venues() -> None:
    venue = make_venue(name="This Hall")
    other = make_venue(name="Other Hall")
    elsewhere_booking = approved(other.id, "2026-10-12", "2026-10-12", 540, 720)
    elsewhere_block = block(other.id, "2026-10-12", "2026-10-12", 1080, 1440)

    built = build_calendar(venue, "2026-10", [elsewhere_block], [elsewhere_booking])

    assert built.days[11].entries == []
    assert [(r.start_minute, r.end_minute) for r in built.days[11].free] == [(420, 1440)]
