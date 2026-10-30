"""SCRUM-25: the event's coordinator checks registered attendees in over HTTP.

The repository is faked (see registration_support.py); the real database
function, including the Asia/Singapore event-day rule, is proven by
database/verify_event_attendance.sql.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from registration_support import (
    ATTENDEE_A,
    NOW,
    FakeCoordinatorAssignments,
    FakeRegistrationRepository,
    add_event,
    add_registration,
    fill,
    make_client,
    make_unauthenticated_client,
)

COORDINATOR_1 = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
COORDINATOR_2 = "c2c2c2c2-c2c2-4c2c-8c2c-c2c2c2c2c2c2"


def check_in_path(event_id: str, registration_id: str) -> str:
    return f"/event-requests/{event_id}/registrations/{registration_id}/check-in"


def setup(*coordinators: str, registered: int = 1, **event: object):
    """A Confirmed event whose only date is NOW's Singapore day."""
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, **{"proposed_date_times": [NOW], **event})
    fill(repo, event_id, registered)
    repo.assignments = FakeCoordinatorAssignments(
        [{"event_request_id": event_id, "coordinator_id": c}
         for c in coordinators or (COORDINATOR_1,)]
    )
    return repo, event_id


def as_coordinator(repo, caller_id: str = COORDINATOR_1, roles=("event_coordinator",)):
    return make_client(repo, caller_id=caller_id, roles=roles, coordinators=repo.assignments)


# AC1-H1, AC2 (happy): checked in on the event day; the clock and coordinator reach the database
def test_coordinator_checks_attendee_in() -> None:
    repo, event_id = setup(registered=2)
    target, other = repo.registrations

    with as_coordinator(repo) as client:
        response = client.post(check_in_path(event_id, target["id"]))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == target["id"]
    assert body["status"] == "Registered"
    assert body["checked_in_by"] == COORDINATOR_1
    assert body["attended_at"].startswith("2030-01-15T12:00:00")
    assert repo.check_in_calls == [(event_id, target["id"], COORDINATOR_1, NOW)]
    assert other.get("attended_at") is None


# AC1-N2 (negative): off the event day is refused and nothing changes
def test_off_the_event_day_is_refused() -> None:
    repo, event_id = setup(proposed_date_times=[NOW + timedelta(days=2)])
    row = repo.registrations[0]

    with as_coordinator(repo) as client:
        response = client.post(check_in_path(event_id, row["id"]))

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Check-in is only open on the event's days",
        "code": "not_event_day",
    }
    assert row.get("attended_at") is None


# AC3-H1 (happy): the view counts attended and absent and shows each row's check-in time
def test_view_shows_attended_and_absent() -> None:
    repo, event_id = setup(registered=3)
    first = repo.registrations[0]

    with as_coordinator(repo) as client:
        client.post(check_in_path(event_id, first["id"]))
        view = client.get(f"/event-requests/{event_id}/registrations").json()

    assert (view["attended"], view["absent"], view["registered"]) == (1, 2, 3)
    attended = {r["id"]: r["attended_at"] for r in view["registrations"]}
    assert attended[first["id"]].startswith("2030-01-15T12:00:00")
    assert sum(value is None for value in attended.values()) == 2


# AC4-N1 (negative): a registration from another event is not found here
def test_other_events_registration_is_not_found() -> None:
    repo, event_id = setup()
    other_event = add_event(repo, proposed_date_times=[NOW])
    fill(repo, other_event, 1)
    foreign = repo.registrations[-1]

    with as_coordinator(repo) as client:
        response = client.post(check_in_path(event_id, foreign["id"]))

    assert response.status_code == 404
    assert response.json()["code"] == "registration_not_found"
    assert foreign.get("attended_at") is None


# AC4-N2 (negative): an unknown registration id
def test_unknown_registration_is_not_found() -> None:
    repo, event_id = setup()

    with as_coordinator(repo) as client:
        response = client.post(check_in_path(event_id, str(uuid4())))

    assert response.status_code == 404
    assert response.json()["code"] == "registration_not_found"


# AC4-N3 (negative): a second check-in is refused and keeps the first time and coordinator
def test_second_check_in_is_refused() -> None:
    repo, event_id = setup()
    row = repo.registrations[0]

    with as_coordinator(repo) as client:
        client.post(check_in_path(event_id, row["id"]))
        first = dict(row)
        response = client.post(check_in_path(event_id, row["id"]))

    assert response.status_code == 409
    assert response.json()["code"] == "already_checked_in"
    assert row == first


# AC1-N4 (negative): a coordinator reassigned away is told the event is not found
def test_reassigned_coordinator_is_not_found() -> None:
    repo, event_id = setup(COORDINATOR_1, COORDINATOR_2)
    row = repo.registrations[0]

    with as_coordinator(repo, caller_id=COORDINATOR_1) as client:
        response = client.post(check_in_path(event_id, row["id"]))

    assert response.status_code == 404
    assert response.json()["code"] == "event_not_found"
    assert row.get("attended_at") is None


# AC1-N5 (negative): no session is refused before any lookup
def test_no_session_is_unauthorised() -> None:
    with make_unauthenticated_client() as client:
        response = client.post(check_in_path(str(uuid4()), str(uuid4())))

    assert response.status_code == 401


# AC1-P2…P4 (partition): only coordinators check people in
@pytest.mark.parametrize("role", ["event_organiser", "venue_staff", "attendee"],
                         ids=["AC1-P2", "AC1-P3", "AC1-P4"])
def test_other_roles_are_forbidden(role: str) -> None:
    repo, event_id = setup()

    with as_coordinator(repo, roles=(role,)) as client:
        response = client.post(check_in_path(event_id, repo.registrations[0]["id"]))

    assert response.status_code == 403
    assert repo.check_in_calls == []


# AC3-N2 (negative): a checked-in attendee can't withdraw; 409 and the row is unchanged
def test_checked_in_attendee_cannot_withdraw() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    registration_id = add_registration(
        repo, event_id, ATTENDEE_A, attended_at=NOW, checked_in_by=COORDINATOR_1
    )

    with make_client(repo) as client:
        response = client.post(f"/attendee/registrations/{registration_id}/withdrawal")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This attendee is already checked in",
        "code": "already_checked_in",
    }
    row = repo.registrations[0]
    assert (row["status"], row["withdrawn_at"], row["attended_at"]) == (
        "Registered",
        None,
        NOW,
    )
