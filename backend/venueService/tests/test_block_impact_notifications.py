"""SCRUM-23 AC3: a new block notifies Coordinators of the bookings it affects.

An approved booking request is the confirmed booking (0018). A block that
shares a date and slot with an approved booking that has not ended notifies
that booking's requesting Coordinator; the block is still saved. Case IDs
match docs/testcases/scrum_23_testcases.md.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.block_repository import block_repository
from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_notifications import (
    BookingNotifier,
    current_venue_date,
    get_booking_notifier,
)
from app.booking_repository import booking_repository
from app.main import app

client = TestClient(app)
TODAY = date(2026, 11, 15)


class RecordingNotifier(BookingNotifier):
    def __init__(self) -> None:
        super().__init__(None)
        self.sent: list[dict] = []

    def send(self, event: dict) -> None:
        self.sent.append(event)


@pytest.fixture
def notifier():
    recorder = RecordingNotifier()
    app.dependency_overrides[get_booking_notifier] = lambda: recorder
    app.dependency_overrides[current_venue_date] = lambda: TODAY
    return recorder


def make_venue(name: str = "Riverside Hall") -> str:
    response = client.post("/venues", json={"name": name, "location": "Campus", "max_capacity": 50})
    assert response.status_code == 201
    return response.json()["id"]


def book(venue_id: str, start: str, end: str, slots: list[str], status: str = "approved", **extra) -> BookingRequest:
    return booking_repository.create(
        BookingRequest(
            venue_id=venue_id,
            requested_by=extra.pop("requested_by", str(uuid4())),
            event_request_id=str(uuid4()),
            event_name=extra.pop("event_name", "Open day"),
            start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end),
            slots=slots,
            status=BookingRequestStatus(status),
        )
    )


def block(venue_id: str, start: str, end: str, slots: list[str], **extra):
    body = {"start_date": start, "end_date": end, "slots": slots, "reason_category": "maintenance"} | extra
    return client.post(f"/venues/{venue_id}/blocks", json=body)


# AC3-H1 (happy): a block over an approved upcoming booking notifies its requesting Coordinator
def test_block_over_a_booking_notifies_its_coordinator(notifier):
    venue = make_venue()
    booking = book(venue, "2026-11-20", "2026-11-21", ["AM", "PM"])

    response = block(venue, "2026-11-21", "2026-11-22", ["AM"], reason_detail="Air-con repairs")

    assert response.status_code == 201
    saved = response.json()
    [event] = notifier.sent
    assert event["event_type"] == "venue_block_affects_booking"
    assert event["recipient_id"] == booking.requested_by
    assert event["event_id"].startswith("block-impact:") and len(event["event_id"]) <= 64
    assert event["payload"] == {
        "block_id": saved["id"],
        "booking_request_id": booking.id,
        "event_request_id": booking.event_request_id,
        "event_name": "Open day",
        "venue_id": venue,
        "venue_name": "Riverside Hall",
        "block_start_date": "2026-11-21",
        "block_end_date": "2026-11-22",
        "block_slots": ["AM"],
        "reason_category": "maintenance",
        "reason_detail": "Air-con repairs",
        "booking_start_date": "2026-11-20",
        "booking_end_date": "2026-11-21",
        "booking_slots": ["AM", "PM"],
    }


# AC3-H2 (happy): every affected booking's Coordinator is notified once
def test_each_affected_booking_is_notified_once(notifier):
    venue = make_venue()
    first = book(venue, "2026-11-20", "2026-11-20", ["AM"])
    second = book(venue, "2026-11-21", "2026-11-21", ["PM"])

    assert block(venue, "2026-11-20", "2026-11-21", ["AM", "PM"]).status_code == 201

    assert sorted(e["recipient_id"] for e in notifier.sent) == sorted([first.requested_by, second.requested_by])
    assert len({e["event_id"] for e in notifier.sent}) == 2


# AC3-P1 (partition): pending or rejected requests, other venues and non-overlapping bookings are not notified
def test_unaffected_bookings_are_not_notified(notifier):
    venue, other = make_venue(), make_venue("Orchard Studio")
    book(venue, "2026-11-20", "2026-11-20", ["AM"], status="pending")
    book(venue, "2026-11-20", "2026-11-20", ["AM"], status="rejected")
    book(other, "2026-11-20", "2026-11-20", ["AM"])
    book(venue, "2026-11-20", "2026-11-20", ["PM"])
    book(venue, "2026-11-23", "2026-11-24", ["AM"])

    assert block(venue, "2026-11-20", "2026-11-22", ["AM"]).status_code == 201

    assert notifier.sent == []


# AC3-B1 (boundary): a booking ending today is upcoming; one that ended yesterday is not
@pytest.mark.parametrize(
    "booking_end,expected",
    [("2026-11-14", 0), ("2026-11-15", 1)],
    ids=["AC3-B1a", "AC3-B1b"],
)
def test_only_bookings_that_have_not_ended_are_notified(notifier, booking_end, expected):
    venue = make_venue()
    book(venue, "2026-11-10", booking_end, ["AM"])

    assert block(venue, "2026-11-01", "2026-11-30", ["AM"]).status_code == 201

    assert len(notifier.sent) == expected


# AC3-N1 (negative): a notification failure never fails or undoes the block
def test_notification_failure_still_saves_the_block(monkeypatch):
    def unreachable(*args, **kwargs):
        raise httpx.ConnectError("notification service down")

    monkeypatch.setattr("app.booking_notifications.httpx.post", unreachable)
    app.dependency_overrides[get_booking_notifier] = lambda: BookingNotifier("http://notifications.invalid/events")
    app.dependency_overrides[current_venue_date] = lambda: TODAY
    venue = make_venue()
    book(venue, "2026-11-20", "2026-11-20", ["AM"])

    response = block(venue, "2026-11-20", "2026-11-20", ["AM"])

    assert response.status_code == 201
    assert block_repository.get(response.json()["id"]) is not None


# AC3-N2 (negative): a refused block sends nothing
def test_refused_block_sends_nothing(notifier):
    venue = make_venue()
    book(venue, "2026-11-20", "2026-11-20", ["AM"])

    assert block(venue, "2026-11-20", "2026-11-19", ["AM"]).status_code == 422
    assert client.post(
        "/venues/missing/blocks",
        json={"start_date": "2026-11-20", "end_date": "2026-11-20", "slots": ["AM"], "reason_category": "safety"},
    ).status_code == 404

    assert notifier.sent == []
