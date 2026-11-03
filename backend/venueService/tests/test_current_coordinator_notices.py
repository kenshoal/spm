"""SCRUM-23 AC7 and SCRUM-63 AC5 (hotfix 2, H10): who is told about a block and about a replacement.

A block notice and the decision on a replacement booking go to the event's current assigned
Coordinator, looked up when the notice is sent, never to a former Coordinator. An ordinary
decision keeps its recipient: the Coordinator who made the request (SCRUM-15 AC4, SCRUM-36 AC3).
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_block_impact_notifications import RecordingNotifier, make_venue
from time_support import slot_times

from app import booking_decision_store
from app.block_repository import block_repository
from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_notifications import (
    current_venue_date,
    get_booking_notifier,
)
from app.booking_repository import booking_repository
from app.coordinator_lookup import (
    CoordinatorLookup,
    CoordinatorLookupError,
    SupabaseCoordinatorLookup,
    get_coordinator_lookup,
)
from app.main import app
from app.organiser_lookup import OrganiserLookup, get_organiser_lookup

client = TestClient(app)
TODAY = date(2026, 11, 15)
FORMER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CURRENT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


class FakeCoordinators(CoordinatorLookup):
    def __init__(self, current: str | None = CURRENT, fail: bool = False) -> None:
        self.current = current
        self.fail = fail
        self.asked: list[str] = []

    def coordinator_of(self, event_request_id: str) -> str | None:
        self.asked.append(event_request_id)
        if self.fail:
            raise CoordinatorLookupError("assignment store down")
        return self.current


@pytest.fixture
def notifier():
    booking_decision_store.memory_decision_store.clear()
    recorder = RecordingNotifier()
    app.dependency_overrides[get_booking_notifier] = lambda: recorder
    app.dependency_overrides[current_venue_date] = lambda: TODAY
    app.dependency_overrides[get_organiser_lookup] = lambda: OrganiserLookup()
    yield recorder
    app.dependency_overrides.pop(get_coordinator_lookup, None)
    app.dependency_overrides.pop(get_organiser_lookup, None)
    booking_decision_store.memory_decision_store.clear()


def use(lookup: CoordinatorLookup) -> CoordinatorLookup:
    app.dependency_overrides[get_coordinator_lookup] = lambda: lookup
    return lookup


def approved_booking(venue_id: str, **extra) -> BookingRequest:
    return booking_repository.create(
        BookingRequest(
            venue_id=venue_id,
            requested_by=FORMER,
            event_request_id=str(uuid4()),
            event_name="Open day",
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 21),
            start_minute=420,
            end_minute=720,
            status=BookingRequestStatus.APPROVED,
            **extra,
        )
    )


def block(venue_id: str):
    return client.post(
        f"/venues/{venue_id}/blocks",
        json={"start_date": "2026-11-20", "end_date": "2026-11-21", **slot_times(["AM"]), "reason_category": "maintenance"},
    )


def pending(venue_id: str, **extra) -> BookingRequest:
    return booking_repository.create(
        BookingRequest(
            venue_id=venue_id,
            requested_by=FORMER,
            event_request_id=str(uuid4()),
            event_name="Open day",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 1),
            start_minute=420,
            end_minute=720,
            **extra,
        )
    )


# AC7-H1 (happy): after a reassignment, the block notice goes to the current Coordinator
# and the former Coordinator who made the booking is not told
def test_a_block_notice_goes_to_the_current_coordinator(notifier):
    lookup = use(FakeCoordinators())
    venue = make_venue()
    booking = approved_booking(venue)

    response = block(venue)

    assert response.status_code == 201
    [event] = notifier.sent
    assert event["event_type"] == "venue_block_affects_booking"
    assert event["recipient_id"] == CURRENT
    assert FORMER not in {sent["recipient_id"] for sent in notifier.sent}
    assert lookup.asked == [booking.event_request_id]


# AC7-P1 (partition): with nobody on record for the event (a local run, or an event without an
# assignment), the notice still goes to the Coordinator who made the booking
def test_without_an_assignment_the_requesting_coordinator_is_told(notifier):
    use(FakeCoordinators(current=None))
    venue = make_venue()
    approved_booking(venue)

    block(venue)

    assert [sent["recipient_id"] for sent in notifier.sent] == [FORMER]


# AC7-N1 (negative): if the current Coordinator cannot be looked up, nobody is told (a former
# Coordinator must not be), and the block is still saved and the booking still flagged
def test_an_unreachable_assignment_store_sends_nothing_but_keeps_the_block(notifier):
    use(FakeCoordinators(fail=True))
    venue = make_venue()
    booking = approved_booking(venue)

    response = block(venue)

    assert response.status_code == 201
    assert notifier.sent == []
    assert len(block_repository.list_for_venue(venue)) == 1
    assert booking_repository.get(booking.id) is not None


# AC5-H1 (happy): approving a replacement booking tells the current Coordinator, not the one
# who made the replacement request
def test_a_replacement_decision_goes_to_the_current_coordinator(notifier):
    use(FakeCoordinators())
    venue = make_venue()
    replacement = pending(venue, replaces_booking_id=str(uuid4()))

    response = client.post(f"/booking-requests/{replacement.id}/decision", json={"decision": "approved"})

    assert response.status_code == 200
    [event] = notifier.sent
    assert event["event_type"] == "venue_booking_approved"
    assert event["recipient_id"] == CURRENT


# AC5-H2 (happy): a rejected replacement tells the current Coordinator too
def test_a_rejected_replacement_goes_to_the_current_coordinator(notifier):
    use(FakeCoordinators())
    venue = make_venue()
    replacement = pending(venue, replaces_booking_id=str(uuid4()))

    response = client.post(
        f"/booking-requests/{replacement.id}/decision", json={"decision": "rejected", "reason": "Not suitable"}
    )

    assert response.status_code == 200
    assert notifier.sent[0]["recipient_id"] == CURRENT


# AC5-N1 (negative): an ordinary booking's decision still goes to the Coordinator who made the
# request (SCRUM-15 AC4), even when the event has a different Coordinator now
def test_an_ordinary_decision_keeps_its_recipient(notifier):
    lookup = use(FakeCoordinators())
    venue = make_venue()
    ordinary = pending(venue)

    client.post(f"/booking-requests/{ordinary.id}/decision", json={"decision": "approved"})

    [event] = notifier.sent
    assert event["recipient_id"] == FORMER
    assert lookup.asked == []


# AC5-N2 (negative): if the current Coordinator of a replacement cannot be looked up, nothing is
# sent, and the decision is still saved
def test_an_unreachable_store_still_saves_a_replacement_decision(notifier):
    use(FakeCoordinators(fail=True))
    venue = make_venue()
    replacement = pending(venue, replaces_booking_id=str(uuid4()))

    response = client.post(f"/booking-requests/{replacement.id}/decision", json={"decision": "approved"})

    assert response.status_code == 200
    assert notifier.sent == []
    assert booking_repository.get(replacement.id).status.value == "approved"


# AC7-H2 (happy): the Supabase lookup reads only the latest assignment row of the one event
def test_the_supabase_lookup_reads_the_latest_assignment():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"coordinator_id": CURRENT}])

    lookup = SupabaseCoordinatorLookup("https://example.supabase.co", "secret", httpx.MockTransport(handler))

    assert lookup.coordinator_of("22222222-2222-4222-8222-222222222222") == CURRENT
    [request] = seen
    assert request.url.path == "/rest/v1/event_coordinator_assignments"
    assert request.url.params["event_request_id"] == "eq.22222222-2222-4222-8222-222222222222"
    assert request.url.params["order"] == "id.desc"
    assert request.url.params["limit"] == "1"
    assert request.url.params["select"] == "coordinator_id"


# AC7-N2 (negative): no assignment and a malformed id give no Coordinator (never a guess); a store error is a lookup error
def test_the_supabase_lookup_edge_cases():
    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    unknown = SupabaseCoordinatorLookup("https://x.supabase.co", "k", httpx.MockTransport(empty))
    assert unknown.coordinator_of("22222222-2222-4222-8222-222222222222") is None
    assert unknown.coordinator_of("not-a-uuid") is None

    failing = SupabaseCoordinatorLookup("https://x.supabase.co", "k", httpx.MockTransport(broken))
    with pytest.raises(CoordinatorLookupError):
        failing.coordinator_of("22222222-2222-4222-8222-222222222222")
