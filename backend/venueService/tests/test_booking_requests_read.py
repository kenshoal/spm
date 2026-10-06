"""Queue and status-read tests for "Submit a Venue Booking Request" (SCRUM-32).

Every test carries its case ID from docs/testcases/scrum_32_testcases.md.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from booking_support import (
    COORDINATOR,
    EVENT,
    ORGANISER,
    OTHER_COORDINATOR,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    submit_body,
)
from fastapi.testclient import TestClient

from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import booking_repository
from app.dependencies import require_authenticated, require_venue_staff
from app.main import app
from app.models import Slot

client = TestClient(app)
AUTH = {"Authorization": "Bearer token"}
BASE_TIME = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _restore_overrides() -> None:
    yield
    app.dependency_overrides.pop(require_venue_staff, None)


def seed(minutes: int = 0, **overrides: Any) -> BookingRequest:
    """Store a request directly, so any status can be set up."""

    fields: dict[str, Any] = {
        "venue_id": "venue-1",
        "requested_by": COORDINATOR,
        "event_request_id": EVENT,
        "start_date": date(2030, 1, 10),
        "end_date": date(2030, 1, 10),
        "slots": [Slot.AM],
        "created_at": BASE_TIME + timedelta(minutes=minutes),
    }
    fields.update(overrides)
    return booking_repository.create(BookingRequest(**fields))


def seed_approved(**overrides: Any) -> BookingRequest:
    return seed(
        status=BookingRequestStatus.APPROVED,
        decided_by=STAFF,
        decided_at=BASE_TIME + timedelta(days=1),
        **overrides,
    )


def seed_rejected(**overrides: Any) -> BookingRequest:
    return seed(
        status=BookingRequestStatus.REJECTED,
        decision_reason="Venue under maintenance",
        suggested_alternative="Try Hall B",
        decided_by=STAFF,
        decided_at=BASE_TIME + timedelta(days=1),
        **overrides,
    )


# AC3-H2 (happy): a submitted request appears in the pending queue with status pending
def test_submitted_request_appears_in_the_pending_queue() -> None:
    fake = FakeEventService()
    fake.add_event()
    as_user(COORDINATOR, "event_coordinator", events=fake)
    venue = make_venue()
    created = client.post(
        "/booking-requests", json=submit_body(venue.id), headers=AUTH
    ).json()

    as_user(STAFF, "venue_staff")
    response = client.get("/booking-requests")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [created["id"]]
    assert response.json()[0]["status"] == "pending"


# AC3-H3 (happy): the queue is oldest first
def test_queue_is_oldest_first() -> None:
    oldest, middle, newest = seed(minutes=0), seed(minutes=5), seed(minutes=10)
    as_user(STAFF, "venue_staff")

    ids = [item["id"] for item in client.get("/booking-requests").json()]

    assert ids == [oldest.id, middle.id, newest.id]


# AC3-P1 (partition): the default queue excludes approved and rejected requests
def test_default_queue_is_pending_only() -> None:
    pending = seed()
    seed_approved()
    seed_rejected()
    as_user(STAFF, "venue_staff")

    response = client.get("/booking-requests")

    assert [item["id"] for item in response.json()] == [pending.id]


# AC3-P2 (partition): status=approved returns only approved requests
def test_status_filter_returns_only_that_status() -> None:
    seed()
    approved = seed_approved()
    seed_rejected()
    as_user(STAFF, "venue_staff")

    response = client.get("/booking-requests", params={"status": "approved"})

    assert [item["id"] for item in response.json()] == [approved.id]


# AC3-B1 (boundary): an empty queue returns an empty list
def test_empty_queue_returns_an_empty_list() -> None:
    as_user(STAFF, "venue_staff")

    response = client.get("/booking-requests")

    assert response.status_code == 200
    assert response.json() == []


# AC3-N1 (negative): an unknown status filter is refused
def test_unknown_status_filter_is_refused() -> None:
    as_user(STAFF, "venue_staff")

    response = client.get("/booking-requests", params={"status": "cancelled"})

    assert response.status_code == 422


# AC3-N2, AC3-N3 (negative): coordinators and organisers cannot read the queue
@pytest.mark.parametrize(
    ("user_id", "role"),
    [(COORDINATOR, "event_coordinator"), (ORGANISER, "event_organiser")],
    ids=["AC3-N2", "AC3-N3"],
)
def test_queue_is_for_venue_staff_only(user_id: str, role: str) -> None:
    seed()
    as_user(user_id, role)

    response = client.get("/booking-requests")

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


# AC3-X2, AC5-X2 (cross-cutting): an unauthenticated caller is refused on every read
@pytest.mark.parametrize(
    "path",
    ["/booking-requests", "/booking-requests/mine", "/booking-requests/some-id"],
    ids=["AC3-X2", "AC5-X2-mine", "AC5-X2-one"],
)
def test_reads_require_authentication(path: str) -> None:
    seed()
    app.dependency_overrides.pop(require_authenticated, None)
    app.dependency_overrides.pop(require_venue_staff, None)

    response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


# AC5-H1 (happy): a Coordinator sees only their own requests, newest first
def test_coordinator_sees_only_their_own_requests_newest_first() -> None:
    older = seed(minutes=0)
    seed(minutes=3, requested_by=OTHER_COORDINATOR)
    newer = seed(minutes=6)
    as_user(COORDINATOR, "event_coordinator")

    response = client.get("/booking-requests/mine")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [newer.id, older.id]
    assert all(item["status"] == "pending" for item in response.json())


# AC5-H2 (happy): a Coordinator opens their own request and sees its status
def test_coordinator_opens_their_own_request() -> None:
    own = seed()
    as_user(COORDINATOR, "event_coordinator")

    response = client.get(f"/booking-requests/{own.id}")

    assert response.status_code == 200
    assert response.json()["id"] == own.id
    assert response.json()["status"] == "pending"


# AC5-P4 (partition): an approved request shows as approved
def test_approved_request_shows_as_approved() -> None:
    approved = seed_approved()
    as_user(COORDINATOR, "event_coordinator")

    body = client.get(f"/booking-requests/{approved.id}").json()

    assert body["status"] == "approved"
    assert body["decided_by"] == STAFF
    assert body["decided_at"] is not None
    assert body["decision_reason"] is None


# AC5-P5 (partition): a rejected request shows its reason and suggested alternative
def test_rejected_request_shows_reason_and_alternative() -> None:
    rejected = seed_rejected()
    as_user(COORDINATOR, "event_coordinator")

    body = client.get(f"/booking-requests/{rejected.id}").json()

    assert body["status"] == "rejected"
    assert body["decision_reason"] == "Venue under maintenance"
    assert body["suggested_alternative"] == "Try Hall B"


# AC5-N14 (negative): another Coordinator's request returns the same 404 as an unknown id
def test_other_coordinators_request_looks_like_an_unknown_id() -> None:
    theirs = seed(requested_by=OTHER_COORDINATOR)
    as_user(COORDINATOR, "event_coordinator")

    other = client.get(f"/booking-requests/{theirs.id}")
    unknown = client.get("/booking-requests/00000000-0000-4000-8000-000000000000")

    assert other.status_code == unknown.status_code == 404
    assert other.json() == unknown.json() == {"detail": "Booking request not found"}


# AC5-N15 (negative): an unknown id returns 404
def test_unknown_request_returns_404() -> None:
    as_user(COORDINATOR, "event_coordinator")

    response = client.get("/booking-requests/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert response.json() == {"detail": "Booking request not found"}


# AC5-N16 (negative): a malformed id returns 404, not 500
def test_malformed_request_id_returns_404() -> None:
    as_user(COORDINATOR, "event_coordinator")

    response = client.get("/booking-requests/not-a-uuid")

    assert response.status_code == 404


# AC5-N17 (negative): organisers cannot read booking requests
def test_organisers_cannot_read_booking_requests() -> None:
    own = seed(requested_by=ORGANISER)
    as_user(ORGANISER, "event_organiser")

    mine = client.get("/booking-requests/mine")
    one = client.get(f"/booking-requests/{own.id}")

    assert mine.status_code == one.status_code == 403
    assert mine.json() == one.json() == {"detail": "Insufficient permissions"}


# AC5-X1 (cross-cutting): venue staff can open any request
def test_venue_staff_can_open_any_request() -> None:
    theirs = seed(requested_by=OTHER_COORDINATOR)
    as_user(STAFF, "venue_staff")

    response = client.get(f"/booking-requests/{theirs.id}")

    assert response.status_code == 200
    assert response.json()["id"] == theirs.id


# AC2-X1 (cross-cutting): the snapshot does not change when the event is edited afterwards
def test_snapshot_is_unaffected_by_later_event_edits() -> None:
    fake = FakeEventService()
    fake.add_event()
    as_user(COORDINATOR, "event_coordinator", events=fake)
    venue = make_venue()
    created = client.post(
        "/booking-requests", json=submit_body(venue.id), headers=AUTH
    ).json()

    fake.add_event(event_name="Renamed Gala", expected_attendance=999)
    body = client.get(f"/booking-requests/{created['id']}").json()

    assert body["event_name"] == "Annual Gala"
    assert body["expected_attendance"] == 120
