"""SCRUM-22: withdrawing a registration over HTTP.

The repository is faked (see registration_support.py); the real database
function is proven by database/verify_registration_withdrawal.sql.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
    CLOSES,
    NON_CONFIRMED,
    NOW,
    FakeRegistrationRepository,
    add_event,
    add_registration,
    fill,
    make_client,
    make_unauthenticated_client,
)

from app.repositories import SupabaseRepositoryError
from app.repositories.registration_repository import RegistrationRpcError

START = datetime(2030, 2, 1, 18, 0, tzinfo=UTC)
NOT_PERMITTED = {
    "detail": "This registration can no longer be withdrawn",
    "code": "withdrawal_not_permitted",
}
ALREADY_WITHDRAWN = {
    "detail": "This registration is already withdrawn",
    "code": "already_withdrawn",
}
NOT_FOUND = {"detail": "Registration not found", "code": "registration_not_found"}


def withdraw_path(registration_id: str) -> str:
    return f"/attendee/registrations/{registration_id}/withdrawal"


def setup(**event_overrides):  # type: ignore[no-untyped-def]
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, **event_overrides)
    registration_id = add_registration(repo, event_id, ATTENDEE_A)
    return repo, event_id, registration_id


# AC1-H1 (happy): an attendee withdraws their own registration
def test_attendee_withdraws_own_registration() -> None:
    repo, event_id, registration_id = setup()
    other_id = add_registration(repo, event_id, ATTENDEE_B)

    with make_client(repo) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == registration_id
    assert body["status"] == "Withdrawn"
    assert body["withdrawn_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert body["event"]["id"] == event_id
    assert body["event"]["places_remaining"] == 9
    stored = {r["id"]: r for r in repo.registrations}
    assert stored[registration_id]["status"] == "Withdrawn"
    assert stored[other_id]["status"] == "Registered"


# AC1-H2 (happy): withdrawal still works after the registration window closed
def test_withdraw_after_registration_window_closed() -> None:
    repo, _, registration_id = setup(registration_closes_at=NOW - timedelta(days=1))

    with make_client(repo) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 200
    assert response.json()["status"] == "Withdrawn"


# AC2-P1 (partition): one representative per non-Confirmed status is refused
@pytest.mark.parametrize("status", NON_CONFIRMED)
def test_withdraw_refused_for_non_confirmed_event(status: str) -> None:
    repo, _, registration_id = setup(status=status)

    with make_client(repo) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 409
    assert response.json() == NOT_PERMITTED
    assert repo.registrations[0]["status"] == "Registered"
    assert repo.registrations[0]["withdrawn_at"] is None


# AC1-B2 (boundary): the event has started, so the API refuses and nothing changes
def test_withdraw_refused_once_event_started() -> None:
    repo, _, registration_id = setup(
        proposed_date_times=[NOW - timedelta(seconds=1)]
    )

    with make_client(repo) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 409
    assert response.json() == NOT_PERMITTED
    assert repo.registrations[0]["status"] == "Registered"


# AC2-N1 (negative): withdrawing twice is 409 and keeps the first timestamp
def test_withdraw_twice_is_already_withdrawn() -> None:
    repo, _, registration_id = setup()

    with make_client(repo) as client:
        first = client.post(withdraw_path(registration_id))
        second = client.post(withdraw_path(registration_id))

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json() == ALREADY_WITHDRAWN
    assert repo.registrations[0]["withdrawn_at"] == NOW


# AC2-N2 (negative): another attendee's registration is 404 and unchanged
def test_withdraw_someone_elses_registration_is_not_found() -> None:
    repo, event_id, _ = setup()
    bs_id = add_registration(repo, event_id, ATTENDEE_B)

    with make_client(repo, caller_id=ATTENDEE_A) as client:
        response = client.post(withdraw_path(bs_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert next(r for r in repo.registrations if r["id"] == bs_id)["status"] == (
        "Registered"
    )


# AC2-N3 (negative): an unknown registration id is 404
def test_withdraw_unknown_registration_is_not_found() -> None:
    with make_client(FakeRegistrationRepository()) as client:
        response = client.post(withdraw_path(str(uuid4())))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


# AC2-N4 (negative): a malformed id is rejected before any lookup
def test_withdraw_malformed_id_is_422() -> None:
    with make_client(FakeRegistrationRepository()) as client:
        response = client.post(withdraw_path("not-a-uuid"))

    assert response.status_code == 422


class StaleReadRepository(FakeRegistrationRepository):
    """Reads say the event is Confirmed, but the locked write finds it Cancelled."""

    def get_event(self, event_id):  # type: ignore[no-untyped-def]
        event = super().get_event(event_id)
        if event is not None:
            event["status"] = "Confirmed"
        return event


# AC2-N5 (negative): the database refusal wins over a stale pre-check
def test_database_refusal_overrides_stale_precheck() -> None:
    repo = StaleReadRepository()
    event_id = add_event(repo, status="Cancelled")
    registration_id = add_registration(repo, event_id, ATTENDEE_A)

    with make_client(repo) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 409
    assert response.json() == NOT_PERMITTED
    assert repo.registrations[0]["status"] == "Registered"


class UnknownRefusalRepository(FakeRegistrationRepository):
    def withdraw(self, registration_id, attendee_id, now):  # type: ignore[no-untyped-def]
        raise RegistrationRpcError("odd", "P9999", "something else")


# AC2-N7 (negative): an unrecognised database refusal is not hidden as a success
def test_unrecognised_refusal_is_a_502() -> None:
    repo = UnknownRefusalRepository()
    event_id = add_event(repo)
    registration_id = add_registration(repo, event_id, ATTENDEE_A)

    with make_client(repo) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 502


class DownRepository(FakeRegistrationRepository):
    def get_registration(self, registration_id):  # type: ignore[no-untyped-def]
        raise SupabaseRepositoryError("down")


# AC2-N6 (negative): an unavailable database is a 502, not a false success
def test_withdraw_when_database_is_down_is_502() -> None:
    with make_client(DownRepository()) as client:
        response = client.post(withdraw_path(str(uuid4())))

    assert response.status_code == 502


# AC2-X1 (cross-cutting): other roles cannot withdraw
@pytest.mark.parametrize("role", ["organiser", "coordinator", "operations_manager"])
def test_other_roles_are_forbidden(role: str) -> None:
    repo, _, registration_id = setup()

    with make_client(repo, roles=(role,)) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 403
    assert repo.registrations[0]["status"] == "Registered"


# AC2-X2 (cross-cutting): no session is 401
def test_withdraw_without_session_is_401() -> None:
    with make_unauthenticated_client() as client:
        response = client.post(withdraw_path(str(uuid4())))

    assert response.status_code == 401


# AC3-H1 (happy): withdrawing raises places remaining by one
def test_withdrawal_frees_a_place() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=5)
    fill(repo, event_id, 4)
    registration_id = add_registration(repo, event_id, ATTENDEE_A)

    with make_client(repo) as client:
        before = client.get(f"/attendee/events/{event_id}").json()
        client.post(withdraw_path(registration_id))
        after = client.get(f"/attendee/events/{event_id}").json()

    assert before["places_remaining"] == 0
    assert after["places_remaining"] == 1


# AC3-H2 (happy): a freed place can be taken by another attendee
def test_freed_place_can_be_taken_by_someone_else() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo, registration_capacity=1)
    registration_id = add_registration(repo, event_id, ATTENDEE_A)

    with make_client(repo, caller_id=ATTENDEE_B) as other:
        full = other.post(f"/attendee/events/{event_id}/registrations")
    with make_client(repo, caller_id=ATTENDEE_A) as client:
        client.post(withdraw_path(registration_id))
    with make_client(repo, caller_id=ATTENDEE_B) as other:
        taken = other.post(f"/attendee/events/{event_id}/registrations")

    assert full.status_code == 409
    assert full.json()["code"] == "event_full"
    assert taken.status_code == 201
    active = [r for r in repo.registrations if r["status"] == "Registered"]
    assert len(active) == 1


# AC3-H3 (happy): a withdrawn attendee can register again (D3)
def test_withdrawn_attendee_can_register_again() -> None:
    repo, event_id, registration_id = setup()

    with make_client(repo) as client:
        client.post(withdraw_path(registration_id))
        again = client.post(f"/attendee/events/{event_id}/registrations")

    assert again.status_code == 201
    assert again.json()["id"] != registration_id
    statuses = sorted(r["status"] for r in repo.registrations)
    assert statuses == ["Registered", "Withdrawn"]


# AC3-N1 (negative): re-registering after the window closed is still refused
def test_cannot_register_again_after_window_closed() -> None:
    repo, event_id, registration_id = setup(registration_closes_at=CLOSES)
    repo.events[event_id]["registration_closes_at"] = NOW - timedelta(seconds=1)

    with make_client(repo) as client:
        client.post(withdraw_path(registration_id))
        again = client.post(f"/attendee/events/{event_id}/registrations")

    assert again.status_code == 409
    assert again.json()["code"] == "registration_not_open"


# AC4-H1 (happy): the list shows Registered and Withdrawn with timestamps
def test_list_shows_withdrawn_registration_with_timestamp() -> None:
    repo, _, registration_id = setup()
    other_event = add_event(repo)
    kept_id = add_registration(repo, other_event, ATTENDEE_A)

    with make_client(repo) as client:
        client.post(withdraw_path(registration_id))
        body = client.get("/attendee/registrations").json()

    by_id = {r["id"]: r for r in body}
    assert set(by_id) == {registration_id, kept_id}
    assert by_id[registration_id]["status"] == "Withdrawn"
    assert by_id[registration_id]["withdrawn_at"] is not None
    assert by_id[kept_id]["status"] == "Registered"
    assert by_id[kept_id]["withdrawn_at"] is None


# AC4-N1 (negative): another attendee does not see a withdrawn registration
def test_other_attendee_does_not_see_withdrawn_registration() -> None:
    repo, _, registration_id = setup()

    with make_client(repo, caller_id=ATTENDEE_A) as client:
        client.post(withdraw_path(registration_id))
    with make_client(repo, caller_id=ATTENDEE_B) as other:
        body = other.get("/attendee/registrations").json()

    assert body == []


class SpyRepository(FakeRegistrationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.withdraw_calls = 0

    def withdraw(self, registration_id, attendee_id, now):  # type: ignore[no-untyped-def]
        self.withdraw_calls += 1
        return super().withdraw(registration_id, attendee_id, now)


# AC2-N2 (negative): the service refuses a stranger's id before it reaches the write
def test_not_owner_never_reaches_the_write() -> None:
    repo = SpyRepository()
    event_id = add_event(repo)
    bs_id = add_registration(repo, event_id, ATTENDEE_B)

    with make_client(repo, caller_id=ATTENDEE_A) as client:
        response = client.post(withdraw_path(bs_id))

    assert response.status_code == 404
    assert repo.withdraw_calls == 0


# AC1-B2 / AC2-N1 (boundary, negative): refusals the rules can see skip the write
@pytest.mark.parametrize(
    ("event_overrides", "registration_overrides", "code"),
    [
        ({"status": "Cancelled"}, {}, "withdrawal_not_permitted"),
        ({"proposed_date_times": [NOW]}, {}, "withdrawal_not_permitted"),
        ({}, {"status": "Withdrawn", "withdrawn_at": NOW}, "already_withdrawn"),
    ],
)
def test_early_refusals_never_reach_the_write(
    event_overrides, registration_overrides, code  # type: ignore[no-untyped-def]
) -> None:
    repo = SpyRepository()
    event_id = add_event(repo, **event_overrides)
    registration_id = add_registration(
        repo, event_id, ATTENDEE_A, **registration_overrides
    )

    with make_client(repo) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 409
    assert response.json()["code"] == code
    assert repo.withdraw_calls == 0
