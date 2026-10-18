"""SCRUM-60 AC2: the Safety Officer reads what a safety check needs, read-only.

Case IDs are from docs/testcases/scrum_60_testcases.md (increment 3).
"""

from booking_support import (
    EVENT,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    seed_booking,
)
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAFETY = "66666666-6666-4666-8666-666666666666"


def block_for(venue_id: str) -> dict:
    as_user(STAFF, "venue_staff")
    response = client.post(
        f"/venues/{venue_id}/blocks",
        json={
            "start_date": "2026-11-20",
            "end_date": "2026-11-20",
            "slots": ["AM"],
            "reason_category": "safety",
        },
    )
    assert response.status_code == 201
    return response.json()


# AC2-H2 (happy): the Safety Officer lists any event's venue bookings without
# being assigned to it.
def test_safety_officer_lists_an_events_bookings() -> None:
    events = FakeEventService()
    events.add_event()
    booking = seed_booking()
    as_user(SAFETY, "safety_officer", events=events)

    response = client.get(f"/booking-requests/event/{EVENT}")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [booking.id]
    assert events.calls == []  # role-wide, like Venue Staff


# AC2-H3 (happy): the Safety Officer reads the venue's size, layouts and
# accessibility features.
def test_safety_officer_reads_a_venue() -> None:
    venue = make_venue(max_capacity=300)
    as_user(SAFETY, "safety_officer")

    response = client.get(f"/venues/{venue.id}")

    assert response.status_code == 200
    assert response.json()["max_capacity"] == 300


# AC2-H4 (happy): the Safety Officer reads the venue's blocks (its restrictions).
def test_safety_officer_reads_venue_blocks() -> None:
    venue = make_venue()
    block = block_for(venue.id)
    as_user(SAFETY, "safety_officer")

    response = client.get(f"/venues/{venue.id}/blocks")

    assert response.status_code == 200
    assert response.json() == [block]


# AC2-N2 (negative): reading is all the Safety Officer can do here.
def test_safety_officer_cannot_change_venues_or_blocks() -> None:
    venue = make_venue()
    as_user(SAFETY, "safety_officer")

    assert client.patch(f"/venues/{venue.id}", json={"max_capacity": 1}).status_code == 403
    assert client.post(
        f"/venues/{venue.id}/blocks",
        json={"start_date": "2026-11-20", "end_date": "2026-11-20", "slots": ["AM"],
              "reason_category": "safety"},
    ).status_code == 403
