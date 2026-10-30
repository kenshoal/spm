"""Replacing a venue for a booking that a block flagged (SCRUM-63 AC4, AC5).

Every test carries its case ID from docs/testcases/scrum_63_testcases.md. The event
service is faked at the HTTP boundary, so the real client runs. A booking is flagged
the way production flags it: by a venue block over it (the database does this in
create_venue_block, 0064; the in-memory store mirrors it).
"""

from datetime import date, timedelta

import pytest
from booking_support import (
    BASE_TIME,
    COORDINATOR,
    ORGANISER,
    OTHER_COORDINATOR,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    seed_booking,
)
from fastapi.testclient import TestClient

from app.booking_models import BookingRequestStatus
from app.booking_notifications import (
    BookingNotifier,
    current_venue_date,
    get_booking_notifier,
)
from app.booking_repository import booking_repository
from app.dependencies import require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer coordinator-token"}
UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
DAY = date(2030, 3, 10)


class QuietNotifier(BookingNotifier):
    def __init__(self) -> None:
        super().__init__(None)

    def send(self, event: dict) -> None:
        return None


@pytest.fixture(autouse=True)
def _quiet_notices() -> None:
    app.dependency_overrides[get_booking_notifier] = QuietNotifier
    app.dependency_overrides[current_venue_date] = lambda: DAY - timedelta(days=30)
    yield
    app.dependency_overrides.pop(get_booking_notifier, None)
    app.dependency_overrides.pop(current_venue_date, None)


@pytest.fixture
def events() -> FakeEventService:
    fake = FakeEventService()
    fake.add_event()
    as_user(COORDINATOR, "event_coordinator", events=fake)
    return fake


def approved(venue_id: str, start_minute: int = 540, end_minute: int = 720, **extra):
    return seed_booking(
        venue_id=venue_id,
        start_date=DAY,
        end_date=DAY,
        start_minute=start_minute,
        end_minute=end_minute,
        status=BookingRequestStatus.APPROVED,
        decided_by=STAFF,
        decided_at=BASE_TIME,
        **extra,
    )


def flag(events: FakeEventService, venue_id: str, start_minute: int = 600, end_minute: int = 660) -> None:
    """Block the venue as Venue Staff, which flags the bookings it affects."""
    as_user(STAFF, "venue_staff", events=events)
    response = client.post(
        f"/venues/{venue_id}/blocks",
        json={
            "start_date": DAY.isoformat(),
            "end_date": DAY.isoformat(),
            "start_minute": start_minute,
            "end_minute": end_minute,
            "reason_category": "maintenance",
        },
    )
    assert response.status_code == 201
    as_user(COORDINATOR, "event_coordinator", events=events)


def replace(booking_id: str, venue_id: str | None, headers: dict | None = AUTH):
    body = {} if venue_id is None else {"venue_id": venue_id}
    return client.post(f"/booking-requests/{booking_id}/replacement", json=body, headers=headers or {})


def decide(booking_id: str, decision: str = "approved", **extra):
    return client.post(
        f"/booking-requests/{booking_id}/decision", json={"decision": decision, **extra}
    )


@pytest.fixture
def flagged(events: FakeEventService):
    blocked = make_venue(name="Blocked Hall")
    other = make_venue(name="Second Hall")
    booking = approved(blocked.id)
    flag(events, blocked.id)
    return blocked, other, booking


# AC4-H1 (happy): the assigned coordinator requests a replacement for a flagged booking
def test_coordinator_requests_a_replacement(flagged) -> None:
    _blocked, other, booking = flagged
    before = booking.model_dump(mode="json")

    response = replace(booking.id, other.id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["venue_id"] == other.id
    assert body["event_request_id"] == booking.event_request_id
    assert (body["start_date"], body["end_date"]) == (DAY.isoformat(), DAY.isoformat())
    assert (body["start_minute"], body["end_minute"]) == (540, 720)
    assert body["replaces_booking_id"] == booking.id
    assert body["requested_by"] == COORDINATOR
    assert body["event_name"] == "Annual Gala"
    assert body["expected_attendance"] == 120
    assert booking_repository.get(body["id"]) is not None
    assert booking_repository.get(booking.id).model_dump(mode="json") == before


# AC4-N1 (negative): a booking with no flag cannot be replaced
def test_an_unflagged_booking_is_refused(events: FakeEventService) -> None:
    blocked, other = make_venue(name="A"), make_venue(name="B")
    booking = approved(blocked.id)
    count = len(booking_repository.list_for_event(booking.event_request_id))

    response = replace(booking.id, other.id)

    assert response.status_code == 409
    assert response.json() == {"detail": "Booking is not flagged as needing a new venue"}
    assert len(booking_repository.list_for_event(booking.event_request_id)) == count


# AC4-N2 (negative): a booking that is not approved cannot be replaced
def test_a_pending_booking_is_refused(events: FakeEventService) -> None:
    blocked, other = make_venue(name="A"), make_venue(name="B")
    pending = seed_booking(venue_id=blocked.id, start_date=DAY, end_date=DAY, start_minute=540, end_minute=720)
    booking_repository.mark_needs_new_venue(pending.id)

    response = replace(pending.id, other.id)

    assert response.status_code == 409
    assert response.json() == {"detail": "Booking is not approved"}


# AC4-N3 (negative): the blocked venue is refused as the replacement
def test_the_same_venue_is_refused(flagged) -> None:
    blocked, _other, booking = flagged

    response = replace(booking.id, blocked.id)

    assert response.status_code == 422
    assert response.json() == {"detail": "A replacement must be at a different venue"}
    assert len(booking_repository.list_for_event(booking.event_request_id)) == 1


# AC4-N4 (negative): an unknown venue is refused
def test_an_unknown_venue_is_refused(flagged) -> None:
    _blocked, _other, booking = flagged

    response = replace(booking.id, UNKNOWN_ID)

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}
    assert len(booking_repository.list_for_event(booking.event_request_id)) == 1


# AC4-N5 (negative): a second replacement while one is active is refused
def test_a_second_active_replacement_is_refused(flagged) -> None:
    _blocked, other, booking = flagged
    third = make_venue(name="Third Hall")
    assert replace(booking.id, other.id).status_code == 201

    response = replace(booking.id, third.id)

    assert response.status_code == 409
    assert response.json() == {"detail": "A replacement has already been requested"}
    assert len(booking_repository.list_for_event(booking.event_request_id)) == 2


# AC4-N7, AC4-N8 (negative): a coordinator who is not the event's current coordinator is refused
def test_an_unassigned_coordinator_is_refused(events: FakeEventService, flagged) -> None:
    _blocked, other, booking = flagged
    as_user(OTHER_COORDINATOR, "event_coordinator", events=events)

    response = replace(booking.id, other.id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Event request not found"}
    assert len(booking_repository.list_for_event(booking.event_request_id)) == 1


# AC4-N9 (negative): an unknown booking id
def test_an_unknown_booking_is_refused(events: FakeEventService) -> None:
    other = make_venue()

    response = replace(UNKNOWN_ID, other.id)

    assert response.status_code == 404
    assert response.json() == {"detail": "Booking request not found"}


# AC4-P1 (partition): roles other than coordinator are refused, and no token is 401
@pytest.mark.parametrize(
    ("role", "user_id", "status_code"),
    [("venue_staff", STAFF, 403), ("event_organiser", ORGANISER, 403), ("safety_officer", ORGANISER, 403)],
    ids=["staff", "organiser", "safety-officer"],
)
def test_other_roles_are_refused(flagged, events: FakeEventService, role: str, user_id: str, status_code: int) -> None:
    _blocked, other, booking = flagged
    as_user(user_id, role, events=events)

    response = replace(booking.id, other.id)

    assert response.status_code == status_code
    assert len(booking_repository.list_for_event(booking.event_request_id)) == 1


def test_a_request_without_a_token_is_refused(flagged) -> None:
    _blocked, other, booking = flagged
    app.dependency_overrides.pop(require_authenticated, None)
    app.dependency_overrides.pop(require_venue_staff, None)

    response = replace(booking.id, other.id, headers=None)

    assert response.status_code == 401


# AC4-N10 (negative): the body names a venue and nothing else
@pytest.mark.parametrize("body", [{}, {"venue_id": ""}, {"venue_id": "x", "start_minute": 600}],
                         ids=["missing", "empty", "extra-field"])
def test_the_body_is_validated(flagged, body: dict) -> None:
    _blocked, _other, booking = flagged

    response = client.post(f"/booking-requests/{booking.id}/replacement", json=body, headers=AUTH)

    assert response.status_code == 422
    assert len(booking_repository.list_for_event(booking.event_request_id)) == 1


# AC5-H1 (happy): approving the replacement cancels the old booking and clears its flag
def test_approving_the_replacement_cancels_the_old_booking(flagged, events: FakeEventService) -> None:
    _blocked, other, booking = flagged
    replacement = replace(booking.id, other.id).json()
    as_user(STAFF, "venue_staff", events=events)

    response = decide(replacement["id"])

    assert response.status_code == 200
    assert booking_repository.get(replacement["id"]).status is BookingRequestStatus.APPROVED
    old = booking_repository.get(booking.id)
    assert old.status is BookingRequestStatus.CANCELLED
    assert old.cancelled_by == STAFF
    assert old.cancelled_at is not None
    assert old.decided_by == STAFF
    assert booking.id not in booking_repository.flagged_ids()


# AC5-N1 (negative): rejecting the replacement leaves the old booking and its flag, and frees the link
def test_rejecting_the_replacement_keeps_the_old_booking(flagged, events: FakeEventService) -> None:
    _blocked, other, booking = flagged
    third = make_venue(name="Third Hall")
    replacement = replace(booking.id, other.id).json()
    as_user(STAFF, "venue_staff", events=events)

    assert decide(replacement["id"], "rejected", reason="Not suitable").status_code == 200

    assert booking_repository.get(booking.id).status is BookingRequestStatus.APPROVED
    assert booking.id in booking_repository.flagged_ids()
    as_user(COORDINATOR, "event_coordinator", events=events)
    assert replace(booking.id, third.id).status_code == 201


# AC5-N2 (negative): a replacement that now clashes is refused and changes nothing
def test_a_clashing_replacement_changes_nothing(flagged, events: FakeEventService) -> None:
    _blocked, other, booking = flagged
    replacement = replace(booking.id, other.id).json()
    approved(other.id, event_request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    as_user(STAFF, "venue_staff", events=events)

    response = decide(replacement["id"])

    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["booking_conflict"]
    assert booking_repository.get(replacement["id"]).status is BookingRequestStatus.PENDING
    assert booking_repository.get(booking.id).status is BookingRequestStatus.APPROVED
    assert booking.id in booking_repository.flagged_ids()


# AC5-N3 (negative): the coordinator cancelling the replacement leaves the old booking and flag
def test_cancelling_the_replacement_keeps_the_old_booking(flagged, events: FakeEventService) -> None:
    _blocked, other, booking = flagged
    replacement = replace(booking.id, other.id).json()

    assert client.post(f"/booking-requests/{replacement['id']}/cancel", headers=AUTH).status_code == 200

    assert booking_repository.get(booking.id).status is BookingRequestStatus.APPROVED
    assert booking.id in booking_repository.flagged_ids()


# AC5-N5 (negative): an original that was already cancelled does not stop the approval
def test_an_already_cancelled_original_does_not_stop_the_approval(flagged, events: FakeEventService) -> None:
    _blocked, other, booking = flagged
    replacement = replace(booking.id, other.id).json()
    assert client.post(f"/booking-requests/{booking.id}/cancel", headers=AUTH).status_code == 200
    as_user(STAFF, "venue_staff", events=events)

    response = decide(replacement["id"])

    assert response.status_code == 200
    assert booking_repository.get(replacement["id"]).status is BookingRequestStatus.APPROVED
    old = booking_repository.get(booking.id)
    assert old.status is BookingRequestStatus.CANCELLED
    assert old.cancelled_by == COORDINATOR
    assert booking.id not in booking_repository.flagged_ids()


# AC5-X2 (cross-cutting): an ordinary approval cancels nothing
def test_an_ordinary_approval_cancels_nothing(events: FakeEventService) -> None:
    venue = make_venue()
    other_booking = approved(venue.id, 840, 900)
    pending = seed_booking(venue_id=venue.id, start_date=DAY, end_date=DAY, start_minute=420, end_minute=480)
    as_user(STAFF, "venue_staff", events=events)

    assert decide(pending.id).status_code == 200

    assert booking_repository.get(pending.id).status is BookingRequestStatus.APPROVED
    assert booking_repository.get(other_booking.id).status is BookingRequestStatus.APPROVED
