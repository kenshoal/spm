"""SCRUM-34: organisers and coordinators view an event's registrations.

The repositories are faked (see registration_support.py); the read-only
endpoint adds no database function or migration.
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

from app.repositories import SupabaseRepositoryError

ORGANISER = "organiser-1"
COORDINATOR_1 = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
COORDINATOR_2 = "c2c2c2c2-c2c2-4c2c-8c2c-c2c2c2c2c2c2"
NOT_FOUND = {"detail": "Event not found", "code": "event_not_found"}


def info_path(event_id: str) -> str:
    return f"/event-requests/{event_id}/registrations"


def as_organiser(repo, caller_id: str = ORGANISER):
    return make_client(repo, caller_id=caller_id, roles=("event_organiser",))


def assigned(event_id: str, *coordinator_ids: str) -> FakeCoordinatorAssignments:
    return FakeCoordinatorAssignments(
        [{"event_request_id": event_id, "coordinator_id": c} for c in coordinator_ids]
    )


def add_registration(repo, event_id: str, status: str, minutes: int) -> dict:
    row = {
        "id": str(uuid4()),
        "event_request_id": event_id,
        "attendee_id": str(uuid4()),
        "status": status,
        "created_at": NOW + timedelta(minutes=minutes),
    }
    repo.registrations.append(row)
    return row


# AC1-H1 (happy): the owning organiser sees their event's registrations and counts
def test_owning_organiser_sees_registrations() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=10)
    fill(repo, event_id, 3)
    before = [dict(r) for r in repo.registrations]

    with as_organiser(repo) as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 200
    body = response.json()
    assert body["event_request_id"] == event_id
    assert len(body["registrations"]) == 3
    assert (body["registered"], body["withdrawn"], body["places_available"]) == (3, 0, 7)
    assert repo.registrations == before


# AC1-N1 (negative): another organiser's event is reported as not found
def test_other_organiser_is_told_not_found() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    fill(repo, event_id, 2)

    with as_organiser(repo, caller_id="organiser-2") as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


# AC2-H1 (happy): the latest-assigned coordinator sees the registrations
def test_assigned_coordinator_sees_registrations() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    fill(repo, event_id, 2)

    with make_client(repo, caller_id=COORDINATOR_1, roles=("event_coordinator",),
                     coordinators=assigned(event_id, COORDINATOR_1)) as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 200
    assert response.json()["registered"] == 2


# AC2-N1 (negative): a coordinator never assigned to the event is told not found
def test_unassigned_coordinator_is_told_not_found() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo, caller_id=COORDINATOR_2, roles=("event_coordinator",),
                     coordinators=assigned(event_id, COORDINATOR_1)) as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


# AC2-N2 (negative): a coordinator reassigned away no longer sees the event
def test_reassigned_coordinator_is_told_not_found() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo, caller_id=COORDINATOR_1, roles=("event_coordinator",),
                     coordinators=assigned(event_id, COORDINATOR_1, COORDINATOR_2)) as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


# AC2-X1 (cross-cutting): a caller with both roles passes through either relationship
def test_caller_with_both_roles_passes_as_coordinator() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)  # owned by organiser-1, not the caller

    with make_client(repo, caller_id=COORDINATOR_1,
                     roles=("event_organiser", "event_coordinator"),
                     coordinators=assigned(event_id, COORDINATOR_1)) as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 200


# AC3-H1 (happy): rows carry exactly the agreed fields, oldest first, for this event only
def test_rows_are_whitelisted_ordered_and_scoped_to_the_event() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    other_id = add_event(repo)
    later = add_registration(repo, event_id, "Registered", minutes=5)
    earlier = add_registration(repo, event_id, "Registered", minutes=1)
    add_registration(repo, other_id, "Registered", minutes=0)

    with as_organiser(repo) as client:
        rows = client.get(info_path(event_id)).json()["registrations"]

    assert [r["id"] for r in rows] == [earlier["id"], later["id"]]
    assert all(
        set(r) == {"id", "attendee_id", "attendee_email", "status", "created_at",
                   "registered_by", "attended_at", "checked_in_by"}
        for r in rows
    )
    assert rows[0]["attendee_id"] == earlier["attendee_id"]
    assert rows[0]["status"] == "Registered"


# AC3-H2 (happy): an event with no registrations is a valid empty result
def test_event_without_registrations_is_empty() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, status="Planning", registration_capacity=None,
                         registration_opens_at=None, registration_closes_at=None)

    with as_organiser(repo) as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 200
    assert response.json() == {
        "event_request_id": event_id,
        "registration_capacity": None,
        "venue_capacity": None,
        "registration_opens_at": None,
        "registration_closes_at": None,
        "registered": 0,
        "withdrawn": 0,
        "places_available": None,
        "attended": 0,
        "absent": 0,
        "registrations": [],
    }


# AC3-P1 (partition): each status lands in its own count (Withdrawn ahead of SCRUM-22)
def test_each_status_is_counted_separately() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=10)
    add_registration(repo, event_id, "Registered", 1)
    add_registration(repo, event_id, "Registered", 2)
    add_registration(repo, event_id, "Withdrawn", 3)

    with as_organiser(repo) as client:
        body = client.get(info_path(event_id)).json()

    assert (body["registered"], body["withdrawn"], body["places_available"]) == (2, 1, 8)
    assert [r["status"] for r in body["registrations"]] == [
        "Registered", "Registered", "Withdrawn"
    ]


# AC3-B1, AC3-B2, AC3-B3 (boundary): one place left, exactly full, capacity unset
@pytest.mark.parametrize(
    ("capacity", "registered", "available"),
    [(5, 4, 1), (5, 5, 0), (None, 0, None)],
    ids=["AC3-B1", "AC3-B2", "AC3-B3"],
)
def test_places_available_at_the_capacity_boundary(
    capacity: int | None, registered: int, available: int | None
) -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=capacity)
    fill(repo, event_id, registered)

    with as_organiser(repo) as client:
        body = client.get(info_path(event_id)).json()

    assert body["registration_capacity"] == capacity
    assert body["places_available"] == available


# AC4-N1 (negative): no session is refused before any lookup
def test_no_session_is_unauthorised() -> None:
    with make_unauthenticated_client() as client:
        response = client.get(info_path(str(uuid4())))

    assert response.status_code == 401


# AC4-P1…P5 (partition): every role other than organiser or coordinator is refused
@pytest.mark.parametrize(
    "role",
    ["attendee", "technical_support", "venue_staff", "event_operations_manager", "admin"],
    ids=["AC4-P1", "AC4-P2", "AC4-P3", "AC4-P4", "AC4-P5"],
)
def test_other_roles_are_forbidden(role: str) -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo, caller_id=ORGANISER, roles=(role,)) as client:
        response = client.get(info_path(event_id))

    assert response.status_code == 403


# AC4-N2 (negative): an unknown event is not found
def test_unknown_event_is_not_found() -> None:
    with as_organiser(FakeRegistrationRepository()) as client:
        response = client.get(info_path(str(uuid4())))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


# AC4-N3 (negative): Supabase being unavailable is reported, not hidden as empty
def test_supabase_unavailable_is_bad_gateway() -> None:
    class DownRepository(FakeRegistrationRepository):
        def get_event_access(self, event_id: str):
            raise SupabaseRepositoryError("Supabase could not complete the registration lookup")

    with as_organiser(DownRepository()) as client:
        response = client.get(info_path(str(uuid4())))

    assert response.status_code == 502
