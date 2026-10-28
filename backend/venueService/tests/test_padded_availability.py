"""SCRUM-66: venue search and the availability check count setup and turnaround.

A booking occupies its venue from start minus setup to end plus turnaround, as
booking approval does (0054), so search never offers a time approval refuses.
Case IDs match docs/testcases/scrum_66_testcases.md. Unless stated, the venue
has 30 minutes setup and 45 turnaround, with A approved 10:00-12:00 on DAY.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import booking_repository
from app.main import app

client = TestClient(app)
DAY = "2026-11-10"


def make_venue(setup: int = 30, turnaround: int = 45) -> str:
    response = client.post(
        "/venues",
        json={
            "name": "Hall",
            "location": "Campus",
            "max_capacity": 50,
            "setup_minutes": setup,
            "turnaround_minutes": turnaround,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def book(venue_id: str, start: int, end: int, status: str = "approved", day: str = DAY) -> str:
    return booking_repository.create(
        BookingRequest(
            venue_id=venue_id,
            requested_by=str(uuid4()),
            event_request_id=str(uuid4()),
            start_date=date.fromisoformat(day),
            end_date=date.fromisoformat(day),
            start_minute=start,
            end_minute=end,
            status=BookingRequestStatus(status),
        )
    ).id


def found(venue_id: str, **params) -> bool:
    response = client.get("/venues/search", params={"date": DAY, **params})
    assert response.status_code == 200
    return venue_id in {venue["id"] for venue in response.json()}


def free_at(venue_id: str, start: int, end: int) -> bool:
    return found(venue_id, start_minute=start, end_minute=end)


def check(venue_id: str, start: int, end: int) -> dict:
    response = client.post(
        f"/venues/{venue_id}/availability",
        json={"start_date": DAY, "end_date": DAY, "start_minute": start, "end_minute": end},
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def venue() -> str:
    venue_id = make_venue()
    book(venue_id, 600, 720)
    return venue_id


# AC1-H1 (happy): a time inside A's turnaround is not offered, though the booked times do not overlap
def test_search_hides_a_time_inside_turnaround(venue: str) -> None:
    assert not free_at(venue, 735, 780)


# AC1-B1 (boundary): after A, a gap of turnaround plus setup is offered; one step less is not
@pytest.mark.parametrize("start,offered", [(795, True), (780, False)], ids=["AC1-B1a", "AC1-B1b"])
def test_search_gap_after_a_booking(venue: str, start: int, offered: bool) -> None:
    assert free_at(venue, start, start + 45) is offered


# AC1-B2 (boundary): the same boundary before A
@pytest.mark.parametrize("end,offered", [(525, True), (540, False)], ids=["AC1-B2a", "AC1-B2b"])
def test_search_gap_before_a_booking(venue: str, end: int, offered: bool) -> None:
    assert free_at(venue, 480, end) is offered


# AC1-B3 (boundary): a time whose own setup or turnaround leaves 07:00-24:00 is not offered
@pytest.mark.parametrize(
    "start,end,offered",
    [(450, 540, True), (435, 540, False), (1320, 1395, True), (1320, 1410, False)],
    ids=["AC1-B3a", "AC1-B3b", "AC1-B3c", "AC1-B3d"],
)
def test_search_needs_padding_inside_the_window(start: int, end: int, offered: bool) -> None:
    assert free_at(make_venue(), start, end) is offered


# AC1-P1 (partition): with no setup or turnaround, search behaves as before
def test_search_without_padding_is_unchanged() -> None:
    venue = make_venue(0, 0)
    book(venue, 600, 720)
    assert free_at(venue, 720, 780)
    assert not free_at(venue, 705, 780)


# AC1-P2 (partition): pending, rejected and cancelled requests never take padded time
@pytest.mark.parametrize("status", ["pending", "rejected", "cancelled"])
def test_search_ignores_requests_that_are_not_approved(status: str) -> None:
    venue = make_venue()
    book(venue, 600, 720, status)
    assert free_at(venue, 735, 780)


# AC1-P3 (partition): blocks are compared without padding, as booking approval does
def test_search_compares_blocks_without_padding() -> None:
    venue = make_venue()
    block = client.post(
        f"/venues/{venue}/blocks",
        json={
            "start_date": DAY, "end_date": DAY, "start_minute": 600, "end_minute": 720,
            "reason_category": "maintenance",
        },
    )
    assert block.status_code == 201
    assert free_at(venue, 720, 780)
    assert not free_at(venue, 705, 780)


# AC1-P4 (partition): another day or another venue is not affected
def test_padding_stays_on_its_venue_and_dates(venue: str) -> None:
    other = make_venue()
    assert free_at(other, 735, 780)
    assert found(venue, start_minute=735, end_minute=780) is False
    response = client.get(
        "/venues/search", params={"date": "2026-11-11", "start_minute": 735, "end_minute": 780}
    )
    assert venue in {v["id"] for v in response.json()}


# AC2-B1 (boundary): with only a date, a day is offered only if some 15-minute booking fits
# with its setup and turnaround
def test_date_only_search_needs_a_padded_gap() -> None:
    venue = make_venue()
    book(venue, 450, 765)  # occupies 07:00-13:30
    book(venue, 930, 1395)  # occupies 15:00-24:00, leaving 13:30-15:00 = 15 + 30 + 45
    assert found(venue)

    tight = make_venue()
    book(tight, 450, 765)
    book(tight, 915, 1395)  # occupies 14:45-24:00, leaving 75 minutes
    assert not found(tight)


# AC2-B2 (boundary): at the start of the day the booking's setup must also fit after 07:00, so
# a gap of 15 minutes plus setup and turnaround from 07:00 just fits and one step less does not
def test_date_only_search_keeps_setup_inside_the_window() -> None:
    venue = make_venue()
    book(venue, 540, 1395)  # occupies 08:30-24:00, leaving 07:00-08:30 = 30 + 15 + 45
    assert found(venue)

    short = make_venue()
    book(short, 525, 1395)  # occupies 08:15-24:00, leaving 75 minutes
    assert not found(short)


# AC2-P1 (partition): with no setup or turnaround, one free 15-minute step is enough
def test_date_only_search_without_padding_is_unchanged() -> None:
    venue = make_venue(0, 0)
    book(venue, 420, 1425)
    assert found(venue)
    book(venue, 1425, 1440)
    assert not found(venue)


# AC3-H1 (happy): the availability check reports a padded clash with its padded overlap
def test_availability_check_reports_a_padded_clash(venue: str) -> None:
    result = check(venue, 735, 780)
    assert result["available"] is False
    assert result["reasons"] == ["booking_conflict"]
    [overlap] = result["booking_conflicts"]
    assert (overlap["start_minute"], overlap["end_minute"]) == (705, 765)


# AC3-B1 (boundary): the exact gap is available
def test_availability_check_allows_the_exact_gap(venue: str) -> None:
    result = check(venue, 795, 840)
    assert result["available"] is True
    assert result["reasons"] == []


# AC3-B2 (boundary): padding outside 07:00-24:00 is reported with approval's codes, and an
# overlap that starts before 07:00 is reported from 07:00
def test_availability_check_reports_window_codes() -> None:
    venue = make_venue()
    book(venue, 450, 540)
    result = check(venue, 435, 480)
    assert result["reasons"] == ["setup_outside_window", "booking_conflict"]
    assert result["booking_conflicts"][0]["start_minute"] == 420
    assert check(make_venue(), 1320, 1410)["reasons"] == ["turnaround_outside_window"]


def calendar_day(venue_id: str) -> tuple[list[tuple[str, int, int]], list[tuple[int, int]]]:
    response = client.get(f"/venues/{venue_id}/calendar", params={"month": DAY[:7]})
    assert response.status_code == 200
    day = next(d for d in response.json()["days"] if d["date"] == DAY)
    return (
        [(e["state"], e["start_minute"], e["end_minute"]) for e in day["entries"]],
        [(r["start_minute"], r["end_minute"]) for r in day["free"]],
    )


# AC4-H1 (happy): the calendar shows a booking with its setup and turnaround as booked
def test_calendar_shows_padded_booking(venue: str) -> None:
    entries, free = calendar_day(venue)
    assert entries == [("booked", 570, 765)]
    assert free == [(420, 570), (765, 1440)]


# AC4-P1 (partition): with no setup or turnaround, the calendar is unchanged
def test_calendar_without_padding_is_unchanged() -> None:
    venue = make_venue(0, 0)
    book(venue, 600, 720)
    assert calendar_day(venue) == ([("booked", 600, 720)], [(420, 600), (720, 1440)])


# AC4-B1 (boundary): padding beyond 07:00-24:00 is cut at the window
def test_calendar_cuts_padding_at_the_window() -> None:
    venue = make_venue(0, 0)
    book(venue, 420, 480)
    book(venue, 1380, 1440)
    assert client.patch(
        f"/venues/{venue}", json={"setup_minutes": 30, "turnaround_minutes": 45}
    ).status_code == 200
    entries, free = calendar_day(venue)
    assert entries == [("booked", 420, 525), ("booked", 1350, 1440)]
    assert free == [(525, 1350)]


# AC4-P2 (partition): a block still wins over a padded booking
def test_calendar_block_wins_over_padding() -> None:
    venue = make_venue()
    book(venue, 600, 720)
    assert client.post(
        f"/venues/{venue}/blocks",
        json={
            "start_date": DAY, "end_date": DAY, "start_minute": 720, "end_minute": 780,
            "reason_category": "maintenance",
        },
    ).status_code == 201
    entries, _ = calendar_day(venue)
    assert entries == [("booked", 570, 720), ("blocked", 720, 780)]


# AC4-X1 (cross-cutting): the first free time on the calendar is offered by search, and the
# step before it is not, so the two views agree
def test_calendar_and_search_agree(venue: str) -> None:
    _, free = calendar_day(venue)
    first_free_after = free[1][0]
    assert first_free_after == 765
    assert free_at(venue, first_free_after + 30, first_free_after + 75)
    assert not free_at(venue, first_free_after + 15, first_free_after + 60)
