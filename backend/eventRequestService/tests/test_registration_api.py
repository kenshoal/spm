"""SCRUM-21: attendee event view and registration over HTTP.

The repository is faked (see registration_support.py); the real database
function is proven by database/verify_event_registrations.sql.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
    NON_CONFIRMED,
    NOW,
    OPENS,
    PUBLIC_KEYS,
    FakeRegistrationRepository,
    add_event,
    fill,
    make_client,
    make_unauthenticated_client,
)

from app.repositories import SupabaseRepositoryError

NOT_FOUND = {"detail": "Event not found", "code": "event_not_found"}


def event_path(event_id: str) -> str:
    return f"/attendee/events/{event_id}"


def register_path(event_id: str) -> str:
    return f"/attendee/events/{event_id}/registrations"


# AC1-H1 (happy): an attendee views a Confirmed event with its public details
def test_attendee_views_confirmed_event() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=10)
    fill(repo, event_id, 3)

    with make_client(repo) as client:
        response = client.get(event_path(event_id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == event_id
    assert body["event_name"] == "Community Dinner"
    assert body["registration_capacity"] == 10
    assert body["places_remaining"] == 7


# AC1-H2 (happy): the list shows only Confirmed events whose window is open now
def test_list_shows_only_confirmed_events_with_open_window() -> None:
    repo = FakeRegistrationRepository()
    open_id = add_event(repo, event_name="Open")
    add_event(repo, event_name="Closed", registration_closes_at=NOW)
    add_event(repo, event_name="Not yet", registration_opens_at=NOW + timedelta(1),
              registration_closes_at=NOW + timedelta(5))
    add_event(repo, event_name="No window", registration_opens_at=None,
              registration_closes_at=None)
    add_event(repo, event_name="Planning", status="Planning")

    with make_client(repo) as client:
        response = client.get("/attendee/events")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [open_id]


# AC1-X1 (cross-cutting): the response keys equal the public whitelist exactly
def test_view_response_has_exactly_the_public_keys() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo) as client:
        single = client.get(event_path(event_id)).json()
        listed = client.get("/attendee/events").json()

    assert set(single) == PUBLIC_KEYS
    assert all(set(item) == PUBLIC_KEYS for item in listed)
    assert "Hall with kitchen" not in str(single)
    assert "organiser-1" not in str(single)


@pytest.mark.parametrize("status", NON_CONFIRMED,
                         ids=[f"AC1-P{k}" for k in range(1, 11)])
# AC1-P1..P10 (partition): an event that isn't Confirmed is reported as not found
def test_non_confirmed_event_is_not_found(status: str) -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, status=status)

    with make_client(repo) as client:
        response = client.get(event_path(event_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


# AC1-N1 (negative): an unknown id is not found
def test_unknown_event_is_not_found() -> None:
    with make_client() as client:
        response = client.get(event_path(str(uuid4())))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


# AC2-H1 (happy): a Confirmed, open, not-full event can be registered for
def test_attendee_registers_for_open_event() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201


@pytest.mark.parametrize("status", NON_CONFIRMED,
                         ids=[f"AC2-P{k}" for k in range(1, 11)])
# AC2-P1..P10 (partition): registering for a non-Confirmed event is refused and stores nothing
def test_register_refused_for_non_confirmed_event(status: str) -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, status=status)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert repo.registrations == []


# AC3-N1 (negative): an event with no window set is not open
def test_register_refused_when_window_not_set() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_opens_at=None,
                         registration_closes_at=None)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "registration_not_open"
    assert repo.registrations == []


# AC3-N2 (negative): registering before the window opens is refused, nothing stored
def test_register_refused_before_window_opens() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_opens_at=NOW + timedelta(seconds=1),
                         registration_closes_at=NOW + timedelta(days=3))

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "registration_not_open"
    assert repo.registrations == []


# AC3-B5 (boundary): at the closing instant the API refuses (exclusive end)
def test_register_refused_exactly_at_closing() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_opens_at=OPENS,
                         registration_closes_at=NOW)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "registration_not_open"
    assert repo.registrations == []


# AC4-B1 (boundary): with one place left the registration succeeds
def test_register_allowed_with_one_place_left() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=5)
    fill(repo, event_id, 4)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    assert response.json()["event"]["places_remaining"] == 0
    assert repo.count_active(event_id) == 5


# AC4-B2 (boundary): when registered equals capacity the API refuses as full, count unchanged
def test_register_refused_when_event_is_full() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=5)
    fill(repo, event_id, 5)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "event_full"
    assert repo.count_active(event_id) == 5


# AC5-H1 (happy): the registration is stored and returned with the public event
def test_successful_registration_is_stored_and_returned() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=10)
    fill(repo, event_id, 3)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    body = response.json()
    assert body["event_request_id"] == event_id
    assert body["attendee_id"] == ATTENDEE_A
    assert body["status"] == "Registered"
    assert body["created_at"]
    assert set(body["event"]) == PUBLIC_KEYS
    assert body["event"]["places_remaining"] == 6
    stored = [r for r in repo.registrations if r["attendee_id"] == ATTENDEE_A]
    assert len(stored) == 1
    assert stored[0]["id"] == body["id"]
    assert stored[0]["status"] == "Registered"


# AC5-H2 (happy): an attendee lists their own registrations, newest first
def test_attendee_lists_own_registrations_newest_first() -> None:
    repo = FakeRegistrationRepository()
    first = add_event(repo, event_name="First")
    second = add_event(repo, event_name="Second")

    with make_client(repo) as client:
        client.post(register_path(first))
        client.post(register_path(second))
        response = client.get("/attendee/registrations")

    assert response.status_code == 200
    body = response.json()
    assert [item["event_request_id"] for item in body] == [second, first]
    assert [item["event"]["event_name"] for item in body] == ["Second", "First"]
    assert all(item["attendee_id"] == ATTENDEE_A for item in body)


# AC5-N1 (negative): another attendee's registrations are not listed
def test_other_attendees_registrations_are_not_listed() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    with make_client(repo, caller_id=ATTENDEE_A) as client:
        assert client.post(register_path(event_id)).status_code == 201

    with make_client(repo, caller_id=ATTENDEE_B) as client:
        response = client.get("/attendee/registrations")

    assert response.status_code == 200
    assert response.json() == []


# AC5-N2 (negative): registering twice is refused as already registered, one row remains
def test_duplicate_registration_is_refused() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo) as client:
        first = client.post(register_path(event_id))
        second = client.post(register_path(event_id))

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "already_registered"
    assert repo.count_active(event_id) == 1


@pytest.mark.parametrize(
    "role", ["event_organiser", "event_coordinator", "event_operations_manager"]
)
# AC5-X1 (cross-cutting): roles other than attendee cannot register, nothing stored
def test_other_roles_cannot_register(role: str) -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo, roles=(role,)) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 403
    assert repo.registrations == []


@pytest.mark.parametrize("role", ["event_organiser", "event_coordinator"])
# AC5-X1 (cross-cutting): other roles are also refused the three read endpoints
def test_other_roles_cannot_read_attendee_endpoints(role: str) -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    with make_client(repo, roles=(role,)) as client:
        statuses = [
            client.get("/attendee/events").status_code,
            client.get(event_path(event_id)).status_code,
            client.get("/attendee/registrations").status_code,
        ]

    assert statuses == [403, 403, 403]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/attendee/events"),
        ("get", "/attendee/events/00000000-0000-4000-8000-000000000001"),
        ("post", "/attendee/events/00000000-0000-4000-8000-000000000001/registrations"),
        ("get", "/attendee/registrations"),
    ],
)
# AC5-X2 (cross-cutting): no session is a 401 on every attendee endpoint
def test_attendee_endpoints_require_a_session(method: str, path: str) -> None:
    with make_unauthenticated_client() as client:
        response = getattr(client, method)(path)

    assert response.status_code == 401


# AC4-N2 (negative): the database is authoritative — if the last place is taken
# between the pre-check and the write, the attendee still gets 409 event_full
def test_database_refusal_after_precheck_maps_to_event_full() -> None:
    class RacingRepository(FakeRegistrationRepository):
        def count_active(self, event_id: str) -> int:
            return 0  # the pre-check sees a free place...

    repo = RacingRepository()
    event_id = add_event(repo, registration_capacity=1)
    fill(repo, event_id, 1)  # ...but the table already holds the last registration

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "event_full"
    assert len(repo.registrations) == 1


# AC5-N3 (negative): an unavailable database is a 502, not a false success
def test_repository_failure_is_a_bad_gateway() -> None:
    class DownRepository(FakeRegistrationRepository):
        def register(self, event_id, attendee_id, now):  # type: ignore[no-untyped-def]
            raise SupabaseRepositoryError("down")

    repo = DownRepository()
    event_id = add_event(repo)

    with make_client(repo) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 502
    assert repo.registrations == []


# AC5-N4 (negative): an attendee holding the last place is refused as already
# registered, not as full — the duplicate check runs before the capacity check,
# matching register_for_event's order
def test_duplicate_registration_on_full_event_is_already_registered() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=1)

    with make_client(repo) as client:
        first = client.post(register_path(event_id))
        second = client.post(register_path(event_id))

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "already_registered"
    assert repo.count_active(event_id) == 1
