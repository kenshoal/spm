"""Reading one event's venue bookings (SCRUM-61).

Every test carries its case ID from docs/testcases/scrum_61_testcases.md. The
event service is faked at the HTTP boundary, so the real client runs.
"""

import pytest
from booking_support import (
    BASE_TIME,
    COORDINATOR,
    EVENT,
    ORGANISER,
    OTHER_COORDINATOR,
    OTHER_EVENT,
    STAFF,
    FakeEventService,
    as_user,
    seed_booking,
)
from fastapi.testclient import TestClient

from app.booking_models import BookingRequestStatus
from app.dependencies import require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer coordinator-token"}


@pytest.fixture
def events() -> FakeEventService:
    fake = FakeEventService()
    fake.add_event()
    as_user(COORDINATOR, "event_coordinator", events=fake)
    return fake


def by_event(event_id: str = EVENT, headers: dict | None = AUTH):
    return client.get(f"/booking-requests/event/{event_id}", headers=headers or {})


def approved(**overrides):
    return seed_booking(
        status=BookingRequestStatus.APPROVED,
        decided_by=STAFF,
        decided_at=BASE_TIME,
        **overrides,
    )


# AC3-H1 (happy): an assigned coordinator lists every booking of the event, oldest first
def test_assigned_coordinator_lists_the_events_bookings_oldest_first(
    events: FakeEventService,
) -> None:
    oldest = seed_booking(minutes=0, venue_id="venue-a")
    middle = seed_booking(minutes=5, venue_id="venue-b")
    newest = seed_booking(minutes=10, venue_id="venue-c")

    response = by_event()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [oldest.id, middle.id, newest.id]
    assert all(item["status"] == "pending" for item in response.json())
    # Only the assignment is checked; the event itself is not read.
    assert [path for path, _auth in events.calls] == [
        f"/event-requests/{EVENT}/coordinator"
    ]


# AC3-H2 (happy): venue staff list the bookings of any event
def test_venue_staff_list_any_events_bookings(events: FakeEventService) -> None:
    first, second = seed_booking(minutes=0), seed_booking(minutes=5)
    as_user(STAFF, "venue_staff", events=events)

    response = by_event()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first.id, second.id]
    assert events.calls == []


# AC3-P1 (partition): bookings of every status are listed
def test_every_status_is_listed(events: FakeEventService) -> None:
    pending = seed_booking(minutes=0)
    accepted = approved(minutes=1)
    rejected = seed_booking(
        minutes=2,
        status=BookingRequestStatus.REJECTED,
        decision_reason="Under repair",
        decided_by=STAFF,
        decided_at=BASE_TIME,
    )

    items = by_event().json()

    assert [(item["id"], item["status"]) for item in items] == [
        (pending.id, "pending"),
        (accepted.id, "approved"),
        (rejected.id, "rejected"),
    ]


# AC3-P2 (partition): only the named event's bookings are returned
def test_only_the_named_events_bookings_are_returned(events: FakeEventService) -> None:
    mine = seed_booking()
    seed_booking(event_request_id=OTHER_EVENT)

    items = by_event().json()

    assert [item["id"] for item in items] == [mine.id]


# AC3-B1 (boundary): an event with no bookings returns an empty list
def test_event_without_bookings_returns_an_empty_list(events: FakeEventService) -> None:
    response = by_event()

    assert response.status_code == 200
    assert response.json() == []


# AC3-N1 (negative): a coordinator not assigned to the event is refused
def test_unassigned_coordinator_is_refused(events: FakeEventService) -> None:
    seed_booking()
    events.add_event(coordinator_id=OTHER_COORDINATOR)

    response = by_event()

    assert response.status_code == 404
    assert response.json() == {"detail": "Event request not found"}


# AC3-N2 (negative): organisers cannot read an event's bookings (A3)
def test_organisers_cannot_read_an_events_bookings(events: FakeEventService) -> None:
    seed_booking()
    as_user(ORGANISER, "event_organiser", events=events)

    response = by_event()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert events.calls == []


# AC3-N3 (negative): a malformed event id is refused
def test_malformed_event_id_is_refused(events: FakeEventService) -> None:
    response = by_event("not-a-uuid")

    assert response.status_code == 422
    assert events.calls == []


# AC3-N4 (negative): an unavailable event service gives 502, never an empty list
@pytest.mark.parametrize("failure", ["connect", "timeout", "500"])
def test_unavailable_event_service_gives_502(
    events: FakeEventService, failure: str
) -> None:
    seed_booking()
    events.failure = failure

    response = by_event()

    assert response.status_code == 502
    assert response.json() == {"detail": "Event request service unavailable"}


# AC3-N5 (negative): a 401 from the event service is passed on
def test_event_service_401_is_passed_on(events: FakeEventService) -> None:
    seed_booking()
    events.failure = "401"

    response = by_event()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid session"}


# AC3-X1 (cross-cutting): a request without a token is refused
def test_by_event_read_requires_authentication(events: FakeEventService) -> None:
    seed_booking()
    app.dependency_overrides.pop(require_authenticated, None)
    app.dependency_overrides.pop(require_venue_staff, None)

    response = by_event(headers=None)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
