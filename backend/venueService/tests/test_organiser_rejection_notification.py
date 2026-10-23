"""SCRUM-36 AC2: the Organiser is told when a venue booking is rejected.

Case IDs match docs/testcases/scrum_36_testcases.md.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from test_booking_notifications import RecordingNotifier, make_request

from app import booking_decision_store
from app.booking_notifications import get_booking_notifier
from app.main import app
from app.organiser_lookup import (
    OrganiserLookup,
    OrganiserLookupError,
    SupabaseOrganiserLookup,
    get_organiser_lookup,
)

client = TestClient(app)
ORGANISER = "11111111-1111-4111-8111-111111111111"


class FakeLookup(OrganiserLookup):
    def __init__(self, organiser_id: str | None = ORGANISER, fail: bool = False) -> None:
        self.organiser_id = organiser_id
        self.fail = fail
        self.asked: list[str] = []

    def organiser_of(self, event_request_id: str) -> str | None:
        self.asked.append(event_request_id)
        if self.fail:
            raise OrganiserLookupError("event store down")
        return self.organiser_id


@pytest.fixture
def notifier():
    booking_decision_store.memory_decision_store.clear()
    recorder = RecordingNotifier()
    app.dependency_overrides[get_booking_notifier] = lambda: recorder
    yield recorder
    app.dependency_overrides.pop(get_organiser_lookup, None)
    booking_decision_store.memory_decision_store.clear()


def use_lookup(lookup: OrganiserLookup) -> OrganiserLookup:
    app.dependency_overrides[get_organiser_lookup] = lambda: lookup
    return lookup


def reject(booking_id: str, **extra: str):
    return client.post(
        f"/booking-requests/{booking_id}/decision",
        json={"decision": "rejected", "reason": "Hall under repair", **extra},
    )


# AC2-H1 (happy): a rejection tells the Organiser as well as the Coordinator, with the
# reason and alternative, and a different key so neither notice hides the other.
def test_rejection_also_notifies_the_organiser(notifier):
    lookup = use_lookup(FakeLookup())
    booking = make_request()

    response = reject(booking.id, suggested_alternative="Try Orchard Studio")

    assert response.status_code == 200
    coordinator_event, organiser_event = notifier.sent
    assert coordinator_event["recipient_id"] == booking.requested_by
    assert organiser_event["event_type"] == "venue_booking_rejected"
    assert organiser_event["recipient_id"] == ORGANISER
    assert organiser_event["event_id"] == f"booking-organiser:{booking.id}"
    assert organiser_event["event_id"] != coordinator_event["event_id"]
    assert organiser_event["payload"] == coordinator_event["payload"]
    assert organiser_event["payload"]["decision_reason"] == "Hall under repair"
    assert organiser_event["payload"]["suggested_alternative"] == "Try Orchard Studio"
    assert lookup.asked == [booking.event_request_id]


# AC2-P1 (partition): an approval tells the Coordinator only; the Organiser can do
# nothing with it, so they are not asked about or told.
def test_approval_does_not_notify_the_organiser(notifier):
    lookup = use_lookup(FakeLookup())
    booking = make_request()

    response = client.post(
        f"/booking-requests/{booking.id}/decision", json={"decision": "approved"}
    )

    assert response.status_code == 200
    [event] = notifier.sent
    assert event["recipient_id"] == booking.requested_by
    assert lookup.asked == []


@pytest.mark.parametrize(
    "lookup",
    [FakeLookup(organiser_id=None), FakeLookup(fail=True)],
    ids=["AC2-N1a", "AC2-N1b"],
)
# AC2-N1 (negative): if the Organiser is unknown or cannot be looked up, the decision
# is still saved and the Coordinator is still told.
def test_missing_organiser_does_not_stop_the_coordinator_notice(notifier, lookup):
    use_lookup(lookup)
    booking = make_request()

    response = reject(booking.id)

    assert response.status_code == 200
    [event] = notifier.sent
    assert event["recipient_id"] == booking.requested_by


# AC2-N2 (negative): a refused or repeated decision tells nobody, and the Organiser
# is not even looked up.
def test_refused_decision_notifies_nobody(notifier):
    lookup = use_lookup(FakeLookup())
    refused = make_request(venue_changes={"status": "blocked"})
    assert (
        client.post(
            f"/booking-requests/{refused.id}/decision", json={"decision": "approved"}
        ).status_code
        == 409
    )
    decided = make_request()
    assert reject(decided.id).status_code == 200
    notifier.sent.clear()
    lookup.asked.clear()

    assert reject(decided.id).status_code == 409

    assert notifier.sent == []
    assert lookup.asked == []


# AC2-N3 (negative): a notification outage on the Organiser's notice does not undo
# the decision.
def test_organiser_notice_outage_does_not_undo_the_decision(monkeypatch):
    from app.booking_notifications import BookingNotifier
    from app.booking_repository import booking_repository

    booking_decision_store.memory_decision_store.clear()
    use_lookup(FakeLookup())

    def unreachable(*args, **kwargs):
        raise httpx.ConnectError("notification service down")

    monkeypatch.setattr("app.booking_notifications.httpx.post", unreachable)
    app.dependency_overrides[get_booking_notifier] = lambda: BookingNotifier(
        "http://notifications.invalid/events"
    )
    booking = make_request()

    response = reject(booking.id)
    app.dependency_overrides.pop(get_organiser_lookup, None)

    assert response.status_code == 200
    assert booking_repository.get(booking.id).status.value == "rejected"


# AC2-H3 (happy): the Supabase lookup reads only the organiser column of the one
# event request, with the service key.
def test_supabase_lookup_asks_for_the_organiser_of_one_event():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"organiser_id": ORGANISER}])

    lookup = SupabaseOrganiserLookup(
        "https://example.supabase.co", "secret", httpx.MockTransport(handler)
    )

    assert lookup.organiser_of("22222222-2222-4222-8222-222222222222") == ORGANISER
    [request] = seen
    assert request.method == "GET"
    assert request.url.path == "/rest/v1/event_requests"
    assert request.url.params["id"] == "eq.22222222-2222-4222-8222-222222222222"
    assert request.url.params["select"] == "organiser_id"


# AC2-N4 (negative): an unknown event, a malformed id, or a store error give no
# Organiser (never a guess); a store error is reported as a lookup error.
def test_supabase_lookup_edge_cases():
    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    unknown = SupabaseOrganiserLookup("https://x.supabase.co", "k", httpx.MockTransport(empty))
    assert unknown.organiser_of("22222222-2222-4222-8222-222222222222") is None
    assert unknown.organiser_of("not-a-uuid") is None

    failing = SupabaseOrganiserLookup("https://x.supabase.co", "k", httpx.MockTransport(broken))
    with pytest.raises(OrganiserLookupError):
        failing.organiser_of("22222222-2222-4222-8222-222222222222")
