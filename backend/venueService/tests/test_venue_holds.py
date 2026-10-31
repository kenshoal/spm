"""SCRUM-18: tentative venue holds through the API, the memory store and the
Supabase store. Case IDs match docs/testcases/scrum_18_testcases.md.

The venue has 30 minutes setup and 45 turnaround; times are on DAY. The database
rules and races are verified in verify_venue_holds.sql and
test_venue_hold_concurrency.py.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from booking_support import (
    COORDINATOR,
    EVENT,
    OTHER_COORDINATOR,
    OTHER_EVENT,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    seed_booking,
)
from fastapi.testclient import TestClient

from app.availability_models import Period
from app.booking_models import BookingRequestStatus
from app.booking_notifications import get_booking_notifier
from app.booking_repository import booking_repository
from app.hold_expiry import hold_notice_event, run_hold_sweep
from app.hold_models import HoldStatus, VenueHold
from app.hold_store import HoldNotActiveError, SupabaseHoldStore, memory_hold_store
from app.main import app

client = TestClient(app)
DAY = date(2030, 3, 4)
HOLD_ID = "5c1f8c0e-8d2f-4c1e-9a55-0e7e3b2a6f10"


@pytest.fixture
def events() -> FakeEventService:
    service = FakeEventService()
    service.add_event()
    as_user(COORDINATOR, "event_coordinator", events=service)
    return service


@pytest.fixture
def venue() -> str:
    return make_venue(setup_minutes=30, turnaround_minutes=45).id


def body(start: int = 600, end: int = 720, *, day: date = DAY, hours: float = 48) -> dict:
    return {
        "event_request_id": EVENT,
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
        "start_minute": start,
        "end_minute": end,
        "expires_at": (datetime.now(UTC) + timedelta(hours=hours)).isoformat(),
    }


def place(venue_id: str, **kwargs: Any) -> httpx.Response:
    return client.post(f"/venues/{venue_id}/holds", json=body(**kwargs))


def placed(venue_id: str, **kwargs: Any) -> dict:
    response = place(venue_id, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


class RecordingNotifier:
    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.events: list[dict] = []

    def send(self, event: dict) -> bool:
        self.events.append(event)
        return self.accept


# AC1-H1 (happy): the assigned coordinator places a hold for their event with an expiry
def test_coordinator_places_a_hold(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    assert hold["status"] == "active"
    assert (hold["venue_id"], hold["event_request_id"], hold["placed_by"]) == (venue, EVENT, COORDINATOR)
    assert (hold["start_minute"], hold["end_minute"]) == (600, 720)


# AC1-B1 (boundary): the expiry must be in the future and at most 7 days ahead
@pytest.mark.parametrize(
    "hours,status_code", [(7 * 24 - 0.01, 201), (7 * 24 + 0.01, 422), (-0.01, 422)],
    ids=["AC1-B1a", "AC1-B1b", "AC1-B1c"],
)
def test_expiry_limits(events: FakeEventService, venue: str, hours: float, status_code: int) -> None:
    assert place(venue, hours=hours).status_code == status_code


# AC1-N1 (negative): only the event's coordinator, only before confirmation, only valid times
def test_who_and_when_can_place(events: FakeEventService, venue: str) -> None:
    as_user(OTHER_COORDINATOR, "event_coordinator", events=events)
    assert place(venue).status_code == 404
    as_user(STAFF, "venue_staff")
    assert place(venue).status_code == 403
    events.add_event(status="Confirmed")
    as_user(COORDINATOR, "event_coordinator", events=events)
    assert place(venue).status_code == 409
    events.add_event(status="Under Review")
    assert place(venue).status_code == 409
    events.add_event(status="Planning")
    assert place(venue, start=610).status_code == 422
    assert memory_hold_store.list_for_event(EVENT) == []


# AC2-H1 (happy): an active hold refuses an overlapping hold, with padding
def test_overlapping_hold_is_refused(events: FakeEventService, venue: str) -> None:
    first = placed(venue)
    response = place(venue, start=735, end=780)
    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["hold_conflict"]
    assert response.json()["detail"]["conflicting_hold_ids"] == [first["id"]]


# AC2-B1 (boundary): a gap equal to setup plus turnaround is free
def test_exact_gap_after_a_hold_is_free(events: FakeEventService, venue: str) -> None:
    placed(venue)
    assert place(venue, start=795, end=840).status_code == 201


# AC2-H2 (happy): an active hold refuses another event's overlapping booking approval
def test_hold_refuses_booking_approval(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    request = seed_booking(
        venue_id=venue, event_request_id=OTHER_EVENT, start_date=DAY, end_date=DAY,
        start_minute=660, end_minute=720,
    )
    as_user(STAFF, "venue_staff")
    response = client.post(f"/booking-requests/{request.id}/decision", json={"decision": "approved"})
    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["hold_conflict"]
    assert response.json()["detail"]["conflicting_hold_ids"] == [hold["id"]]
    assert booking_repository.get(request.id).status is BookingRequestStatus.PENDING


# AC2-P2 (partition): an event's own hold never blocks that event's booking approval
def test_own_event_hold_does_not_block_its_approval(events: FakeEventService, venue: str) -> None:
    placed(venue)
    request = seed_booking(venue_id=venue, start_date=DAY, end_date=DAY, start_minute=660, end_minute=720)
    as_user(STAFF, "venue_staff")
    response = client.post(f"/booking-requests/{request.id}/decision", json={"decision": "approved"})
    assert response.status_code == 200, response.text


# AC2-H3 (happy): a hold over an approved booking is refused
def test_hold_over_a_booking_is_refused(events: FakeEventService, venue: str) -> None:
    booking = seed_booking(
        venue_id=venue, start_date=DAY, end_date=DAY, start_minute=600, end_minute=720,
        status=BookingRequestStatus.APPROVED,
    )
    response = place(venue, start=735, end=780)
    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["booking_conflict"]
    assert response.json()["detail"]["conflicting_booking_ids"] == [booking.id]


def stored_hold(venue_id: str, start: int, end: int, expires_in: timedelta) -> VenueHold:
    return memory_hold_store.add(VenueHold(
        venue_id=venue_id, event_request_id=EVENT, start_date=DAY, end_date=DAY,
        start_minute=start, end_minute=end, placed_by=COORDINATOR,
        expires_at=datetime.now(UTC) + expires_in,
    ))


def expired_hold(venue_id: str, start: int = 600, end: int = 720) -> VenueHold:
    return stored_hold(venue_id, start, end, timedelta(seconds=-1))


# AC3-H1 (happy): an expired hold no longer protects its time, even before the sweep runs
def test_expired_hold_frees_its_time(events: FakeEventService, venue: str) -> None:
    expired_hold(venue)
    assert place(venue).status_code == 201


# AC3-N1 (negative): an expired hold cannot be released or converted
def test_expired_hold_cannot_be_released_or_converted(events: FakeEventService, venue: str) -> None:
    hold = expired_hold(venue)
    assert client.post(f"/venue-holds/{hold.id}/release").status_code == 409
    assert client.post(f"/venue-holds/{hold.id}/convert").status_code == 409


# AC4-H1 (happy): 24 hours before expiry the coordinator gets one "expiring" notice
def test_expiring_notice_is_sent_once(events: FakeEventService, venue: str) -> None:
    hold = placed(venue, hours=30)
    notifier = RecordingNotifier()
    assert run_hold_sweep(memory_hold_store, notifier) == 0
    soon = datetime.now(UTC) + timedelta(hours=7)
    assert run_hold_sweep(memory_hold_store, notifier, soon) == 1
    assert run_hold_sweep(memory_hold_store, notifier, soon) == 0
    [event] = notifier.events
    assert event["event_type"] == "venue_hold_expiring"
    assert event["recipient_id"] == COORDINATOR
    assert event["event_id"] == f"hold-expiring:{hold['id']}"
    assert len(event["event_id"]) <= 64


# AC4-B1 (boundary): a hold placed with less than 24 hours left gets its notice at once
def test_short_hold_is_noticed_when_placed(events: FakeEventService, venue: str) -> None:
    notifier = RecordingNotifier()
    app.dependency_overrides[get_booking_notifier] = lambda: notifier
    hold = placed(venue, hours=3)
    assert [e["event_id"] for e in notifier.events] == [f"hold-expiring:{hold['id']}"]


# AC4-H2 (happy): after expiry the sweep marks the hold expired and sends one "expired" notice
def test_expired_notice_is_sent_once(events: FakeEventService, venue: str) -> None:
    hold = expired_hold(venue)
    notifier = RecordingNotifier()
    assert run_hold_sweep(memory_hold_store, notifier) == 1
    assert run_hold_sweep(memory_hold_store, notifier) == 0
    assert memory_hold_store.get(hold.id).status is HoldStatus.EXPIRED
    assert notifier.events[0]["event_type"] == "venue_hold_expired"


# AC4-P1 (partition): a notice that failed to send is retried on the next sweep
def test_failed_notice_is_retried(events: FakeEventService, venue: str) -> None:
    expired_hold(venue)
    failing = RecordingNotifier(accept=False)
    assert run_hold_sweep(memory_hold_store, failing) == 0
    working = RecordingNotifier()
    assert run_hold_sweep(memory_hold_store, working) == 1


# AC5-H1 (happy): releasing frees the time at once
def test_release_frees_the_time(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    response = client.post(f"/venue-holds/{hold['id']}/release")
    assert response.status_code == 200
    assert response.json()["status"] == "released"
    assert place(venue).status_code == 201


# AC5-N1 (negative): only the event's coordinator can release or convert
def test_only_the_coordinator_can_release_or_convert(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    as_user(OTHER_COORDINATOR, "event_coordinator", events=events)
    assert client.post(f"/venue-holds/{hold['id']}/release").status_code == 404
    assert client.post(f"/venue-holds/{hold['id']}/convert").status_code == 404
    assert client.post("/venue-holds/missing/release").status_code == 404


# AC5-P2 (partition): after a reassignment only the new coordinator can release the hold
def test_reassigned_coordinator_takes_over_the_hold(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    events.add_event(coordinator_id=OTHER_COORDINATOR)
    assert client.post(f"/venue-holds/{hold['id']}/release").status_code == 404
    as_user(OTHER_COORDINATOR, "event_coordinator", events=events)
    assert client.post(f"/venue-holds/{hold['id']}/release").status_code == 200


# AC5-H2 (happy): converting creates a pending request that keeps the hold; approval makes it
# the booking and ends the hold
def test_convert_then_approve(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    response = client.post(f"/venue-holds/{hold['id']}/convert")
    assert response.status_code == 201
    booking = response.json()["booking"]
    assert booking["status"] == "pending"
    assert (booking["venue_id"], booking["start_minute"], booking["end_minute"]) == (venue, 600, 720)
    assert response.json()["hold"]["booking_request_id"] == booking["id"]
    assert place(venue, start=735, end=780).status_code == 409
    assert client.post(f"/venue-holds/{hold['id']}/convert").status_code == 409

    as_user(STAFF, "venue_staff")
    decided = client.post(f"/booking-requests/{booking['id']}/decision", json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    assert memory_hold_store.get(hold["id"]).status is HoldStatus.CONVERTED


# AC5-H3 (happy): a rejected conversion releases its hold
def test_convert_then_reject(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    booking = client.post(f"/venue-holds/{hold['id']}/convert").json()["booking"]
    as_user(STAFF, "venue_staff")
    client.post(
        f"/booking-requests/{booking['id']}/decision",
        json={"decision": "rejected", "reason": "Room unavailable"},
    )
    assert memory_hold_store.get(hold["id"]).status is HoldStatus.RELEASED


# AC3-B3 (boundary): a conversion decided after its hold expired, before the sweep ran, leaves
# the hold to the sweep: it ends as expired, with its notice
@pytest.mark.parametrize("decision", [
    {"decision": "approved"}, {"decision": "rejected", "reason": "Room unavailable"},
])
def test_decision_after_expiry_leaves_the_hold_to_the_sweep(
    events: FakeEventService, venue: str, decision: dict,
) -> None:
    hold = placed(venue)
    booking = client.post(f"/venue-holds/{hold['id']}/convert").json()["booking"]
    memory_hold_store.add(memory_hold_store.get(hold["id"]).model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    ))
    as_user(STAFF, "venue_staff")
    decided = client.post(f"/booking-requests/{booking['id']}/decision", json=decision)
    assert decided.status_code == 200, decided.text
    assert memory_hold_store.get(hold["id"]).status is HoldStatus.ACTIVE
    notifier = RecordingNotifier()
    assert run_hold_sweep(memory_hold_store, notifier) == 1
    assert memory_hold_store.get(hold["id"]).status is HoldStatus.EXPIRED
    assert notifier.events[0]["event_id"] == f"hold-expired:{hold['id']}"


# AC5-P1 (partition): the coordinator lists their event's holds
def test_coordinator_lists_event_holds(events: FakeEventService, venue: str) -> None:
    first = placed(venue)
    second = placed(venue, day=DAY + timedelta(days=1))
    response = client.get("/venue-holds", params={"event_request_id": EVENT})
    assert response.status_code == 200
    assert [h["id"] for h in response.json()] == [first["id"], second["id"]]


def search_result(venue_id: str, *, day: date = DAY, **times: int) -> dict | None:
    """The venue's search match on that day (and times), or None if it is not offered."""
    matches = client.get("/venues/search", params={"date": day.isoformat(), **times}).json()
    return next((v for v in matches if v["id"] == venue_id), None)


# AC6-H1 (happy): search shows a venue held at that time (with padding) as tentatively held,
# a free time as not held, and the availability check reports the hold
def test_search_and_availability_show_holds(events: FakeEventService, venue: str) -> None:
    hold = placed(venue)
    assert search_result(venue, start_minute=735, end_minute=780)["tentatively_held"] is True
    assert search_result(venue, start_minute=900, end_minute=960)["tentatively_held"] is False
    check = client.post(f"/venues/{venue}/availability", json={
        "start_date": DAY.isoformat(), "end_date": DAY.isoformat(),
        "start_minute": 735, "end_minute": 780,
    }).json()
    assert check["reasons"] == ["hold_conflict"]
    assert check["hold_conflicts"][0]["hold_id"] == hold["id"]


# AC6-P2 (partition): a booked time stays hidden from search, and released or expired holds
# are not shown as held
def test_search_hides_booked_time_and_ignores_ended_holds(events: FakeEventService, venue: str) -> None:
    seed_booking(
        venue_id=venue, start_date=DAY, end_date=DAY, start_minute=600, end_minute=720,
        status=BookingRequestStatus.APPROVED,
    )
    hold = stored_hold(venue, 900, 960, timedelta(days=1))
    assert search_result(venue, start_minute=600, end_minute=720) is None
    assert search_result(venue, start_minute=900, end_minute=960)["tentatively_held"] is True
    client.post(f"/venue-holds/{hold.id}/release")
    expired_hold(venue, 1080, 1140)
    assert search_result(venue, start_minute=900, end_minute=960)["tentatively_held"] is False
    assert search_result(venue, start_minute=1080, end_minute=1140)["tentatively_held"] is False


# AC6-B1 (boundary): with only a date, a venue is tentatively held when holds take all of its
# free time that day, and not when some free time is left
def test_date_only_search_marks_a_fully_held_day(events: FakeEventService, venue: str) -> None:
    placed(venue, start=450, end=1395)
    placed(venue, day=DAY + timedelta(days=1))
    assert search_result(venue)["tentatively_held"] is True
    assert search_result(venue, day=DAY + timedelta(days=1))["tentatively_held"] is False


def calendar_day(venue_id: str) -> dict:
    body = client.get(f"/venues/{venue_id}/calendar", params={"month": DAY.strftime("%Y-%m")}).json()
    return next(d for d in body["days"] if d["date"] == DAY.isoformat())


# AC6-H2 (happy): the calendar shows an active hold as held, with padding, and not as free
def test_calendar_shows_held(events: FakeEventService, venue: str) -> None:
    placed(venue)
    day = calendar_day(venue)
    assert [(e["state"], e["start_minute"], e["end_minute"]) for e in day["entries"]] == [
        ("held", 570, 765)
    ]
    assert [(r["start_minute"], r["end_minute"]) for r in day["free"]] == [(420, 570), (765, 1440)]


# AC6-P1 (partition): a booking takes precedence over a hold, and released or expired holds
# do not show
def test_calendar_precedence_and_ended_holds(events: FakeEventService, venue: str) -> None:
    hold = stored_hold(venue, 720, 840, timedelta(days=1))
    seed_booking(
        venue_id=venue, start_date=DAY, end_date=DAY, start_minute=600, end_minute=720,
        status=BookingRequestStatus.APPROVED,
    )
    states = [(e["state"], e["start_minute"], e["end_minute"]) for e in calendar_day(venue)["entries"]]
    assert states == [("booked", 570, 765), ("held", 765, 885)]
    client.post(f"/venue-holds/{hold.id}/release")
    expired_hold(venue, 900, 960)
    assert [e["state"] for e in calendar_day(venue)["entries"]] == ["booked"]


def supabase_store(responses: list[tuple[int, Any]]) -> tuple[SupabaseHoldStore, list[httpx.Request]]:
    sent: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        status_code, payload = queue.pop(0)
        return httpx.Response(status_code, json=payload)

    return SupabaseHoldStore("https://project.supabase.co", "key", transport=httpx.MockTransport(handler)), sent


def hold_row(**overrides: Any) -> dict:
    return {
        "id": HOLD_ID, "venue_id": "2a192261-5e90-4398-90ff-1a2d0eaaff00", "event_request_id": EVENT,
        "start_date": DAY.isoformat(), "end_date": DAY.isoformat(), "start_minute": 600,
        "end_minute": 720, "expires_at": "2030-03-01T00:00:00+00:00", "status": "active",
        "booking_request_id": None, "placed_by": COORDINATOR,
        "placed_at": "2030-02-27T00:00:00+00:00", "closed_at": None, "closed_by": None,
    } | overrides


# AC1-X1 (cross-cutting): the Supabase store calls 0066's functions and maps their answers
def test_supabase_store_calls_the_hold_functions() -> None:
    venue = make_venue()
    store, sent = supabase_store([
        (200, {"outcome": "placed", "hold": hold_row()}),
        (200, {"outcome": "refused", "refusal_codes": ["hold_conflict"],
               "conflicting_block_ids": [], "conflicting_booking_ids": [],
               "conflicting_hold_ids": [HOLD_ID]}),
        (200, [{"hold_id": HOLD_ID, "kind": "expired", "recipient_id": COORDINATOR,
                "venue_id": venue.id, "venue_name": "Hall", "event_request_id": EVENT,
                "event_name": "Gala", "start_date": DAY.isoformat(), "end_date": DAY.isoformat(),
                "start_minute": 600, "end_minute": 720, "expires_at": "2030-03-01T00:00:00+00:00"}]),
        (400, {"code": "55000"}),
    ])
    period = Period(start_date=DAY, end_date=DAY, start_minute=600, end_minute=720)
    expiry = datetime(2030, 3, 1, tzinfo=UTC)

    assert store.place(venue, EVENT, period, expiry, COORDINATOR).hold.id == HOLD_ID
    assert store.place(venue, EVENT, period, expiry, COORDINATOR).conflicting_hold_ids == [HOLD_ID]
    [notice] = store.sweep(expiry)
    assert hold_notice_event(notice)["event_id"] == f"hold-expired:{HOLD_ID}"
    with pytest.raises(HoldNotActiveError):
        store.release(HOLD_ID, COORDINATOR)

    assert sent[0].url.path == "/rest/v1/rpc/place_venue_hold"
    assert json.loads(sent[0].content)["p_expires_at"] == expiry.isoformat()
    assert sent[2].url.path == "/rest/v1/rpc/sweep_venue_holds"
    assert sent[3].url.path == "/rest/v1/rpc/release_venue_hold"


# AC3-P2 (partition): holds read for search, availability and the calendar leave out those of
# Cancelled or Rejected events, as the database guard does
def test_supabase_store_reads_only_holds_of_live_events() -> None:
    store, sent = supabase_store([(200, [hold_row(event_requests={"status": "Planning"})])])
    [hold] = store.list_for_venue(hold_row()["venue_id"], DAY, DAY)
    assert hold.id == HOLD_ID
    params = dict(sent[0].url.params)
    assert params["select"] == "*,event_requests!inner(status)"
    assert params["event_requests.status"] == "not.in.(Cancelled,Rejected)"
    assert params["status"] == "eq.active"
