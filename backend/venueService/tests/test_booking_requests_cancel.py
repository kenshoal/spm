"""Cancelling one venue booking leaves the others alone (SCRUM-61).

Every test carries its case ID from docs/testcases/scrum_61_testcases.md. The
event service is faked at the HTTP boundary, so the real client runs.
"""

import pytest
from booking_support import (
    BASE_TIME,
    COORDINATOR,
    ORGANISER,
    OTHER_COORDINATOR,
    OTHER_EVENT,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    seed_booking,
)
from fastapi.testclient import TestClient

from app.booking_models import BookingRequestStatus
from app.booking_repository import booking_repository
from app.dependencies import require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer coordinator-token"}
UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def events() -> FakeEventService:
    fake = FakeEventService()
    fake.add_event()
    fake.add_event(event_id=OTHER_EVENT, coordinator_id=OTHER_COORDINATOR)
    as_user(COORDINATOR, "event_coordinator", events=fake)
    return fake


def cancel(booking_id: str, headers: dict | None = AUTH):
    return client.post(f"/booking-requests/{booking_id}/cancel", headers=headers or {})


def decide(booking_id: str, decision: str = "approved"):
    return client.post(
        f"/booking-requests/{booking_id}/decision", json={"decision": decision}
    )


def as_coordinator(events: FakeEventService, user_id: str = COORDINATOR) -> None:
    as_user(user_id, "event_coordinator", events=events)


def as_staff(events: FakeEventService) -> None:
    as_user(STAFF, "venue_staff", events=events)


# AC4-H1 (happy): cancelling a pending booking leaves the others as they are
def test_cancelling_a_pending_booking_leaves_the_others(events: FakeEventService) -> None:
    first = seed_booking(minutes=0, venue_id="venue-a")
    second = seed_booking(minutes=1, venue_id="venue-b")

    response = cancel(first.id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_by"] == COORDINATOR
    assert body["cancelled_at"] is not None
    assert booking_repository.get(second.id).status is BookingRequestStatus.PENDING
    assert booking_repository.get(second.id).cancelled_at is None


# AC4-H2 (happy): cancelling an approved booking frees its slots and leaves the sibling approved
def test_cancelling_an_approved_booking_frees_its_slots(events: FakeEventService) -> None:
    hall_a, hall_b = make_venue(name="Hall A"), make_venue(name="Hall B")
    first = seed_booking(minutes=0, venue_id=hall_a.id)
    sibling = seed_booking(minutes=1, venue_id=hall_b.id)
    rival = seed_booking(minutes=2, venue_id=hall_a.id, event_request_id=OTHER_EVENT)
    as_staff(events)
    assert decide(first.id).status_code == 200
    assert decide(sibling.id).status_code == 200
    assert decide(rival.id).status_code == 409  # the slot is taken

    as_coordinator(events)
    assert cancel(first.id).status_code == 200

    as_staff(events)
    assert decide(rival.id).status_code == 200  # the slot is free again
    assert booking_repository.get(sibling.id).status is BookingRequestStatus.APPROVED


# AC4-N1 (negative): a rejected booking cannot be cancelled (A2)
def test_rejected_booking_cannot_be_cancelled(events: FakeEventService) -> None:
    rejected = seed_booking(
        status=BookingRequestStatus.REJECTED,
        decision_reason="Under repair",
        decided_by=STAFF,
        decided_at=BASE_TIME,
    )

    response = cancel(rejected.id)

    assert response.status_code == 409
    assert response.json() == {"detail": "Booking request cannot be cancelled"}
    assert booking_repository.get(rejected.id).status is BookingRequestStatus.REJECTED


# AC4-N2 (negative): a cancelled booking cannot be cancelled again
def test_cancelled_booking_cannot_be_cancelled_again(events: FakeEventService) -> None:
    booking = seed_booking()
    assert cancel(booking.id).status_code == 200
    first_time = booking_repository.get(booking.id).cancelled_at

    response = cancel(booking.id)

    assert response.status_code == 409
    assert booking_repository.get(booking.id).cancelled_at == first_time


# AC4-N3 (negative): a coordinator not assigned to the event cannot cancel
def test_unassigned_coordinator_cannot_cancel(events: FakeEventService) -> None:
    booking = seed_booking()
    events.add_event(coordinator_id=OTHER_COORDINATOR)

    response = cancel(booking.id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Event request not found"}
    assert booking_repository.get(booking.id).status is BookingRequestStatus.PENDING


# AC4-N4 (negative): venue staff and organisers cannot cancel
@pytest.mark.parametrize(
    ("user_id", "role"),
    [(STAFF, "venue_staff"), (ORGANISER, "event_organiser")],
    ids=["AC4-N4-staff", "AC4-N4-organiser"],
)
def test_only_coordinators_can_cancel(
    events: FakeEventService, user_id: str, role: str
) -> None:
    booking = seed_booking()
    as_user(user_id, role, events=events)

    response = cancel(booking.id)

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert booking_repository.get(booking.id).status is BookingRequestStatus.PENDING


# AC4-N5 (negative): an unknown or malformed id returns 404
@pytest.mark.parametrize("booking_id", [UNKNOWN_ID, "not-a-uuid"], ids=["unknown", "malformed"])
def test_unknown_booking_returns_404(events: FakeEventService, booking_id: str) -> None:
    response = cancel(booking_id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Booking request not found"}


# AC4-N6 (negative): cancel follows the current assignment, not the requester
def test_cancel_follows_the_current_assignment(events: FakeEventService) -> None:
    booking = seed_booking(requested_by=COORDINATOR)
    events.add_event(coordinator_id=OTHER_COORDINATOR)  # the event is reassigned

    former = cancel(booking.id)
    assert former.status_code == 404
    assert booking_repository.get(booking.id).status is BookingRequestStatus.PENDING

    as_coordinator(events, OTHER_COORDINATOR)
    current = cancel(booking.id)
    assert current.status_code == 200
    assert current.json()["cancelled_by"] == OTHER_COORDINATOR


# AC4-N7 (negative): an unavailable event service gives 502 and cancels nothing
@pytest.mark.parametrize("failure", ["connect", "timeout", "500"])
def test_unavailable_event_service_cancels_nothing(
    events: FakeEventService, failure: str
) -> None:
    booking = seed_booking()
    events.failure = failure

    response = cancel(booking.id)

    assert response.status_code == 502
    assert booking_repository.get(booking.id).status is BookingRequestStatus.PENDING


# AC4-X1 (cross-cutting): a cancelled booking can no longer be decided
def test_cancelled_booking_cannot_be_decided(events: FakeEventService) -> None:
    venue = make_venue()
    booking = seed_booking(venue_id=venue.id)
    assert cancel(booking.id).status_code == 200

    as_staff(events)
    response = decide(booking.id)

    assert response.status_code == 409
    assert booking_repository.get(booking.id).status is BookingRequestStatus.CANCELLED


# AC4-X2 (cross-cutting): a request without a token is refused
def test_cancel_requires_authentication(events: FakeEventService) -> None:
    booking = seed_booking()
    app.dependency_overrides.pop(require_authenticated, None)
    app.dependency_overrides.pop(require_venue_staff, None)

    response = cancel(booking.id, headers=None)

    assert response.status_code == 401
    assert booking_repository.get(booking.id).status is BookingRequestStatus.PENDING


# AC4-X3 (cross-cutting): the queue and the approved list exclude cancelled requests
def test_cancelled_booking_is_not_in_the_queue_or_the_approved_list(
    events: FakeEventService,
) -> None:
    booking = seed_booking()
    assert cancel(booking.id).status_code == 200

    as_staff(events)
    pending = client.get("/booking-requests").json()
    approved = client.get("/booking-requests", params={"status": "approved"}).json()
    cancelled = client.get("/booking-requests", params={"status": "cancelled"}).json()

    assert booking.id not in [item["id"] for item in pending]
    assert booking.id not in [item["id"] for item in approved]
    assert [item["id"] for item in cancelled] == [booking.id]
