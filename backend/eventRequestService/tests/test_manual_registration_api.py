"""SCRUM-41: a coordinator registers an existing attendee account over HTTP.

The repository is faked (see registration_support.py); the real database
function is proven by database/verify_manual_event_registrations.sql.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from registration_support import (
    NOW,
    FakeCoordinatorAssignments,
    FakeRegistrationRepository,
    add_event,
    fill,
    make_client,
    make_unauthenticated_client,
)

COORDINATOR_1 = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
COORDINATOR_2 = "c2c2c2c2-c2c2-4c2c-8c2c-c2c2c2c2c2c2"
VIP = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1"
VIP_EMAIL = "vip@test.local"


def path(event_id: str) -> str:
    return f"/event-requests/{event_id}/registrations"


def setup(*coordinators: str, **event: object):
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, **event)
    repo.attendee_accounts[VIP_EMAIL] = VIP
    repo.assignments = FakeCoordinatorAssignments(
        [{"event_request_id": event_id, "coordinator_id": c}
         for c in coordinators or (COORDINATOR_1,)]
    )
    return repo, event_id


def as_coordinator(repo, caller_id: str = COORDINATOR_1, roles=("event_coordinator",)):
    return make_client(repo, caller_id=caller_id, roles=roles, coordinators=repo.assignments)


# AC1-H1, AC4-H1 (happy): the assigned coordinator registers an attendee; the row names them
def test_coordinator_registers_attendee_by_email() -> None:
    repo, event_id = setup()

    with as_coordinator(repo) as client:
        response = client.post(path(event_id), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 201
    body = response.json()
    assert body["event_request_id"] == event_id
    assert body["attendee_id"] == VIP
    assert body["status"] == "Registered"
    assert body["registered_by"] == COORDINATOR_1
    assert repo.manual_calls == [(event_id, COORDINATOR_1, VIP_EMAIL)]
    assert len(repo.registrations) == 1


# AC1-H2 (happy): a closed registration window does not stop a coordinator (D2)
def test_coordinator_registers_outside_the_window() -> None:
    repo, event_id = setup(registration_opens_at=NOW - timedelta(days=9),
                           registration_closes_at=NOW - timedelta(days=8))

    with as_coordinator(repo) as client:
        response = client.post(path(event_id), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 201


# AC1-N1 (negative): an unknown email is refused and nothing is stored
def test_unknown_email_is_attendee_not_found() -> None:
    repo, event_id = setup()

    with as_coordinator(repo) as client:
        response = client.post(path(event_id), json={"attendee_email": "nobody@test.local"})

    assert response.status_code == 404
    assert response.json()["code"] == "attendee_not_found"
    assert repo.registrations == []


# AC1-N4 (negative): a missing or blank email is rejected before the database is called
@pytest.mark.parametrize("payload", [{}, {"attendee_email": "   "}], ids=["missing", "blank"])
def test_missing_or_blank_email_is_unprocessable(payload: dict) -> None:
    repo, event_id = setup()

    with as_coordinator(repo) as client:
        response = client.post(path(event_id), json=payload)

    assert response.status_code == 422
    assert repo.manual_calls == []


# AC1-N5 (negative): the attendee already holds a place
def test_duplicate_is_already_registered() -> None:
    repo, event_id = setup()

    with as_coordinator(repo) as client:
        client.post(path(event_id), json={"attendee_email": VIP_EMAIL})
        response = client.post(path(event_id), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This attendee is already registered for this event",
        "code": "already_registered",
    }
    assert len(repo.registrations) == 1


# AC2-B2 (boundary): an exactly full event is refused and the count is unchanged
def test_full_event_is_refused() -> None:
    repo, event_id = setup(registration_capacity=2)
    fill(repo, event_id, 2)

    with as_coordinator(repo) as client:
        response = client.post(path(event_id), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 409
    assert response.json()["code"] == "event_full"
    assert len(repo.registrations) == 2


# AC2-N1 (negative): an event with no capacity set can't take a registration
def test_capacity_not_set_is_refused() -> None:
    repo, event_id = setup(registration_capacity=None)

    with as_coordinator(repo) as client:
        response = client.post(path(event_id), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 409
    assert response.json()["code"] == "capacity_not_set"
    assert repo.registrations == []


# AC3-H1, AC4-H1 (happy): the manual registration shows in SCRUM-34's view and the
# attendee's own list; a self-registration on the same event has no registered_by
def test_manual_registration_is_visible_like_a_self_registration() -> None:
    repo, event_id = setup()
    self_attendee = str(uuid4())
    repo.register(event_id, self_attendee, NOW)

    with as_coordinator(repo) as client:
        client.post(path(event_id), json={"attendee_email": VIP_EMAIL})
        view = client.get(path(event_id)).json()
    with make_client(repo, caller_id=VIP) as client:
        mine = client.get("/attendee/registrations").json()

    by_attendee = {r["attendee_id"]: r["registered_by"] for r in view["registrations"]}
    assert by_attendee == {self_attendee: None, VIP: COORDINATOR_1}
    assert view["registered"] == 2
    assert [r["event_request_id"] for r in mine] == [event_id]


# AC4-N1 (negative): a coordinator reassigned away is told the event is not found
def test_reassigned_coordinator_is_not_found() -> None:
    repo, event_id = setup(COORDINATOR_1, COORDINATOR_2)

    with as_coordinator(repo, caller_id=COORDINATOR_1) as client:
        response = client.post(path(event_id), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 404
    assert response.json()["code"] == "event_not_found"
    assert repo.registrations == []


# AC4-N2 (negative): no session is refused before any lookup
def test_no_session_is_unauthorised() -> None:
    with make_unauthenticated_client() as client:
        response = client.post(path(str(uuid4())), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 401


# AC4-P1…P3 (partition): only coordinators may register someone else
@pytest.mark.parametrize("role", ["event_organiser", "attendee", "admin"],
                         ids=["AC4-P1", "AC4-P2", "AC4-P3"])
def test_other_roles_are_forbidden(role: str) -> None:
    repo, event_id = setup()

    with as_coordinator(repo, roles=(role,)) as client:
        response = client.post(path(event_id), json={"attendee_email": VIP_EMAIL})

    assert response.status_code == 403
    assert repo.manual_calls == []
