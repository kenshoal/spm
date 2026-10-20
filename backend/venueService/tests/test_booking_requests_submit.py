"""Submission tests for "Submit a Venue Booking Request" (SCRUM-32).

Every test carries its case ID from docs/testcases/scrum_32_testcases.md. The
event service is faked at the HTTP boundary, so the real client runs.
"""

import pytest
from booking_support import (
    COORDINATOR,
    EVENT,
    OMIT,
    ORGANISER,
    OTHER_COORDINATOR,
    STAFF,
    FakeEventService,
    as_user,
    make_venue,
    submit_body,
)
from fastapi.testclient import TestClient

from app.booking_repository import booking_repository, get_booking_repository
from app.dependencies import require_authenticated, require_venue_staff
from app.main import app
from app.models import VenueStatus
from app.repository import repository
from app.supabase_repository import SupabaseRepositoryError

client = TestClient(app)
AUTH = {"Authorization": "Bearer coordinator-token"}


@pytest.fixture
def events() -> FakeEventService:
    fake = FakeEventService()
    fake.add_event()
    as_user(COORDINATOR, "event_coordinator", events=fake)
    return fake


def stored_count() -> int:
    return sum(
        len(booking_repository.list_by_status(status))
        for status in ("pending", "approved", "rejected")
    )


def submit(body: dict, headers: dict | None = AUTH):
    return client.post("/booking-requests", json=body, headers=headers or {})


# AC1-H3 (happy): the assigned Coordinator submits a single-day, one-slot request
def test_assigned_coordinator_submits_a_pending_request(events: FakeEventService) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["venue_id"] == venue.id
    assert body["event_request_id"] == EVENT
    assert body["requested_by"] == COORDINATOR
    assert body["start_date"] == "2030-01-10"
    assert body["end_date"] == "2030-01-10"
    assert body["slots"] == ["AM"]
    assert body["id"]
    assert stored_count() == 1


# AC1-H4 (happy): a multi-day request for 07:00-24:00 (all three old slots) is stored
def test_multi_day_request_with_all_slots_is_stored(events: FakeEventService) -> None:
    venue = make_venue()

    response = submit(
        submit_body(venue.id, end_date="2030-01-12", start_minute=420, end_minute=1440)
    )

    assert response.status_code == 201
    assert response.json()["end_date"] == "2030-01-12"
    assert response.json()["slots"] == ["AM", "PM", "NIGHT"]


# AC1-B4, AC1-B5, AC1-B6 (boundary): the end date may equal or follow the start, never precede it
@pytest.mark.parametrize(
    ("end_date", "expected"),
    [("2030-01-09", 422), ("2030-01-10", 201), ("2030-01-11", 201)],
    ids=["AC1-B4", "AC1-B5", "AC1-B6"],
)
def test_end_date_boundary(events: FakeEventService, end_date: str, expected: int) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id, start_date="2030-01-10", end_date=end_date))

    assert response.status_code == expected
    if expected == 422:
        assert response.json()["detail"][0]["loc"] == ["body", "end_date"]
        assert stored_count() == 0
    else:
        assert stored_count() == 1


# AC1-P4, AC1-P5, AC1-P6 (partition): each old slot's time range alone is accepted
@pytest.mark.parametrize(
    ("slot", "start", "end"),
    [("AM", 420, 720), ("PM", 720, 1080), ("NIGHT", 1080, 1440)],
    ids=["AC1-P4", "AC1-P5", "AC1-P6"],
)
def test_each_slot_alone_is_accepted(
    events: FakeEventService, slot: str, start: int, end: int
) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id, start_minute=start, end_minute=end))

    assert response.status_code == 201
    assert response.json()["slots"] == [slot]


# AC1-P7 (partition): a request for dates in the past is accepted (A1)
def test_past_dates_are_accepted(events: FakeEventService) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id, start_date="2020-01-10", end_date="2020-01-10"))

    assert response.status_code == 201
    assert response.json()["status"] == "pending"


# AC1-P8 (partition): a request for a blocked venue is accepted (A1)
def test_blocked_venue_is_accepted(events: FakeEventService) -> None:
    venue = make_venue(status=VenueStatus.BLOCKED.value)

    response = submit(submit_body(venue.id))

    assert response.status_code == 201
    assert response.json()["status"] == "pending"


# AC1-N11, AC1-N12, AC1-N13 (negative): the body may not set requested_by, status or a snapshot field
@pytest.mark.parametrize(
    "extra",
    [
        {"requested_by": OTHER_COORDINATOR},
        {"status": "approved"},
        {"event_name": "Hijacked"},
    ],
    ids=["AC1-N11", "AC1-N12", "AC1-N13"],
)
def test_server_owned_fields_cannot_be_set_by_the_caller(
    events: FakeEventService, extra: dict
) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id, **extra))

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
    assert stored_count() == 0
    assert events.calls == []


# AC1-N14 to AC1-N23 (negative): invalid, missing or retired fields are refused and nothing is stored
@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        # Times replace slots (SCRUM-65); slots are now refused as unknown.
        ({"slots": ["AM"]}, "slots"),
        ({"start_minute": "ten"}, "start_minute"),
        ({"end_minute": None}, "end_minute"),
        ({"start_minute": OMIT}, "start_minute"),
        ({"end_minute": OMIT}, "end_minute"),
        ({"start_date": OMIT}, "start_date"),
        ({"end_date": OMIT}, "end_date"),
        ({"start_date": "2030-02-30"}, "start_date"),
        ({"venue_id": OMIT}, "venue_id"),
        ({"event_request_id": OMIT}, "event_request_id"),
    ],
    ids=[
        "AC1-N14", "AC1-N15", "AC1-N16", "AC1-N17", "AC1-N18",
        "AC1-N19", "AC1-N20", "AC1-N21", "AC1-N22", "AC1-N23",
    ],
)
def test_invalid_fields_are_refused(
    events: FakeEventService, overrides: dict, field: str
) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id, **overrides))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:2] == ["body", field]
    assert stored_count() == 0


# AC1-N24 (negative): an event reference that is not a UUID is refused before any lookup
def test_event_reference_must_be_a_uuid(events: FakeEventService) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id, event_request_id="not-a-uuid"))

    assert response.status_code == 422
    assert stored_count() == 0
    assert events.calls == []


# AC1-N25 (negative): an unknown venue returns 404
def test_unknown_venue_returns_404(events: FakeEventService) -> None:
    response = submit(submit_body("does-not-exist"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue not found"
    assert stored_count() == 0


# AC1-N26 (negative): a request without a bearer token is refused
def test_submit_requires_authentication(events: FakeEventService) -> None:
    venue = make_venue()
    app.dependency_overrides.pop(require_authenticated)

    response = submit(submit_body(venue.id), headers=None)

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert stored_count() == 0
    assert events.calls == []


# AC2-H2 (happy): the snapshot is copied from the event, not from the caller
def test_snapshot_is_copied_from_the_event(events: FakeEventService) -> None:
    venue = make_venue()

    body = submit(submit_body(venue.id)).json()

    assert body["event_name"] == "Annual Gala"
    assert body["expected_attendance"] == 120
    assert body["requirements_note"] == "Stage and projector"


# AC2-P2 (partition): an event with no name, attendance or requirements still yields a request
def test_event_without_snapshot_values_still_yields_a_request(events: FakeEventService) -> None:
    events.add_event(event_name=None, expected_attendance=None, venue_requirements=None)
    venue = make_venue()

    response = submit(submit_body(venue.id))

    assert response.status_code == 201
    body = response.json()
    assert body["event_name"] is None
    assert body["expected_attendance"] is None
    assert body["requirements_note"] is None


# AC4-H2 (happy): two identical pending requests from one Coordinator coexist
def test_identical_pending_requests_coexist(events: FakeEventService) -> None:
    venue = make_venue()

    first = submit(submit_body(venue.id))
    second = submit(submit_body(venue.id))

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert stored_count() == 2


# AC4-H3 (happy): pending requests from two Coordinators for the same slots coexist
def test_requests_from_two_coordinators_coexist(events: FakeEventService) -> None:
    events.add_event(event_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", coordinator_id=OTHER_COORDINATOR)
    venue = make_venue()

    first = submit(submit_body(venue.id))
    as_user(OTHER_COORDINATOR, "event_coordinator", events=events)
    second = submit(
        submit_body(venue.id, event_request_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["status"] == second.json()["status"] == "pending"


# AC4-X2 (cross-cutting): submitting leaves the venue unchanged and writes only the requests
def test_submitting_leaves_the_venue_unchanged(events: FakeEventService) -> None:
    venue = make_venue()
    before = repository.get(venue.id)

    for _ in range(3):
        assert submit(submit_body(venue.id)).status_code == 201

    assert repository.get(venue.id) == before
    assert len(repository.list()) == 1
    assert stored_count() == 3


# AC6-X4 (cross-cutting): a Coordinator not assigned to the event is refused
def test_unassigned_coordinator_is_refused(events: FakeEventService) -> None:
    events.add_event(coordinator_id=OTHER_COORDINATOR)
    venue = make_venue()

    response = submit(submit_body(venue.id))

    assert response.status_code == 404
    assert response.json()["detail"] == "Event request not found"
    assert stored_count() == 0


# AC6-X5, AC6-X6 (cross-cutting): venue staff and organisers cannot submit
@pytest.mark.parametrize(
    ("user_id", "role"),
    [(STAFF, "venue_staff"), (ORGANISER, "event_organiser")],
    ids=["AC6-X5", "AC6-X6"],
)
def test_only_coordinators_can_submit(events: FakeEventService, user_id: str, role: str) -> None:
    venue = make_venue()
    as_user(user_id, role, events=events)

    response = submit(submit_body(venue.id))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    assert stored_count() == 0
    assert events.calls == []


# AC6-N1 (negative): an event that does not exist is refused
def test_unknown_event_is_refused(events: FakeEventService) -> None:
    venue = make_venue()

    response = submit(submit_body(venue.id, event_request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Event request not found"
    assert stored_count() == 0


# AC6-N2 (negative): an unavailable event service gives 502 and stores nothing
@pytest.mark.parametrize("failure", ["connect", "timeout", "500"])
def test_unavailable_event_service_gives_502(events: FakeEventService, failure: str) -> None:
    events.failure = failure
    venue = make_venue()

    response = submit(submit_body(venue.id))

    assert response.status_code == 502
    assert response.json()["detail"] == "Event request service unavailable"
    assert stored_count() == 0


# AC6-N3 (negative): a malformed reply from the event service gives 502
def test_malformed_event_reply_gives_502(events: FakeEventService) -> None:
    events.failure = "malformed"
    venue = make_venue()

    response = submit(submit_body(venue.id))

    assert response.status_code == 502
    assert stored_count() == 0


# AC6-N4 (negative): a 401 from the event service is passed on as 401
def test_event_service_401_is_passed_on(events: FakeEventService) -> None:
    events.failure = "401"
    venue = make_venue()

    response = submit(submit_body(venue.id))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid session"
    assert stored_count() == 0


# AC6-X7 (cross-cutting): the caller's own token reaches the event service
def test_callers_token_is_forwarded_to_the_event_service(events: FakeEventService) -> None:
    venue = make_venue()

    submit(submit_body(venue.id), headers={"Authorization": "Bearer abc"})

    assert events.calls
    assert all(auth == "Bearer abc" for _path, auth in events.calls)


# AC6-X8 (cross-cutting): a store failure gives 502 and no created request
def test_store_failure_gives_502(events: FakeEventService) -> None:
    class BrokenStore:
        def create(self, booking: object) -> object:
            raise SupabaseRepositoryError("Venue store unavailable")

    app.dependency_overrides[get_booking_repository] = lambda: BrokenStore()
    venue = make_venue()

    response = submit(submit_body(venue.id))

    assert response.status_code == 502
    assert stored_count() == 0


@pytest.fixture(autouse=True)
def _reset_overrides() -> None:
    yield
    app.dependency_overrides.pop(get_booking_repository, None)
    app.dependency_overrides.pop(require_venue_staff, None)
