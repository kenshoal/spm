"""SCRUM-15 AC3: an approved booking makes its venue, dates and slots unavailable.

Search and the availability check treat approved requests like active blocks;
pending and rejected requests reserve nothing. Case IDs match
docs/testcases/scrum_15_testcases.md.
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


def make_venue(slots=("AM", "PM")) -> str:
    response = client.post(
        "/venues",
        json={"name": "Hall", "location": "Campus", "max_capacity": 50, "operating_slots": list(slots)},
    )
    assert response.status_code == 201
    return response.json()["id"]


def book(venue_id: str, start: str, end: str, slots: list[str], status="approved") -> str:
    booking = BookingRequest(
        venue_id=venue_id,
        requested_by=str(uuid4()),
        event_request_id=str(uuid4()),
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        slots=slots,
        status=BookingRequestStatus(status),
    )
    return booking_repository.create(booking).id


def search(**params) -> set[str]:
    response = client.get("/venues/search", params=params)
    assert response.status_code == 200
    return {venue["id"] for venue in response.json()}


# AC3-H1 (happy): an approved booking hides its venue from a search for that date and slot
def test_search_excludes_a_booked_slot():
    venue = make_venue()
    book(venue, "2026-10-20", "2026-10-21", ["AM"])

    assert venue not in search(date="2026-10-20", slot="AM")
    assert venue not in search(date="2026-10-21", slot="AM")


# AC3-P1 (partition): pending and rejected requests reserve nothing
@pytest.mark.parametrize("status", ["pending", "rejected"], ids=["AC3-P1a", "AC3-P1b"])
def test_pending_and_rejected_requests_do_not_hide_a_venue(status):
    venue = make_venue()
    book(venue, "2026-10-20", "2026-10-20", ["AM"], status=status)

    assert venue in search(date="2026-10-20", slot="AM")


# AC3-P2 (partition): other slots, other dates and other venues stay offered
def test_other_slots_dates_and_venues_stay_offered():
    venue, other = make_venue(), make_venue()
    book(venue, "2026-10-20", "2026-10-20", ["AM"])

    assert venue in search(date="2026-10-20", slot="PM")
    assert venue in search(date="2026-10-21", slot="AM")
    assert other in search(date="2026-10-20", slot="AM")


# AC3-B1 (boundary): a date-only search needs one operating slot free of blocks and bookings
def test_date_only_search_counts_blocks_and_bookings_together():
    venue = make_venue(slots=("AM", "PM"))
    book(venue, "2026-10-20", "2026-10-20", ["AM"])
    assert venue in search(date="2026-10-20")

    client.post(
        f"/venues/{venue}/blocks",
        json={"start_date": "2026-10-20", "end_date": "2026-10-20", "slots": ["PM"], "reason_category": "safety"},
    )
    assert venue not in search(date="2026-10-20")


# AC3-B2 (boundary): booking dates are inclusive in search
def test_booking_dates_are_inclusive_in_search():
    venue = make_venue()
    book(venue, "2026-10-20", "2026-10-21", ["AM"])

    assert venue in search(date="2026-10-19", slot="AM")
    assert venue not in search(date="2026-10-21", slot="AM")
    assert venue in search(date="2026-10-22", slot="AM")


# AC3-H2 (happy): the availability check reports an approved booking as a conflict
def test_availability_check_reports_booking_conflicts():
    venue = make_venue()
    booked = book(venue, "2026-10-20", "2026-10-21", ["AM"])
    book(venue, "2026-10-20", "2026-10-21", ["AM"], status="pending")

    response = client.post(
        f"/venues/{venue}/availability",
        json={"start_date": "2026-10-21", "end_date": "2026-10-22", "slots": ["AM", "PM"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reasons"] == ["booking_conflict"]
    assert body["booking_conflicts"] == [
        {"booking_id": booked, "start_date": "2026-10-21", "end_date": "2026-10-21", "slots": ["AM"]}
    ]
    assert body["conflicts"] == []


# AC3-P3 (partition): a free period has no booking conflicts
def test_availability_check_free_period():
    venue = make_venue()
    book(venue, "2026-10-20", "2026-10-20", ["AM"])

    response = client.post(
        f"/venues/{venue}/availability",
        json={"start_date": "2026-10-20", "end_date": "2026-10-20", "slots": ["PM"]},
    )

    assert response.json()["available"] is True
    assert response.json()["booking_conflicts"] == []
