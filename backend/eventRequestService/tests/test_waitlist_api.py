"""SCRUM-24: joining and listing the event waiting list over HTTP.

The repository is faked (see waitlist_support.py); the real database function
is proven by database/verify_event_waitlist.sql.
"""

from uuid import uuid4

import pytest
from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
    NON_CONFIRMED,
    NOW,
    add_event,
    add_registration,
    fill,
)
from waitlist_support import (
    OFFERED,
    WAITING,
    FakeWaitlistRepository,
    add_offer,
    add_waitlist_entry,
    make_unauthenticated_waitlist_client,
    make_waitlist_client,
)

NOT_FOUND = {"detail": "Event not found", "code": "event_not_found"}


def join_path(event_id: str) -> str:
    return f"/attendee/events/{event_id}/waitlist"


def full_event(repo: FakeWaitlistRepository, **overrides) -> str:
    """A Confirmed event with every place registered."""
    event_id = add_event(repo, registration_capacity=2, **overrides)
    fill(repo, event_id, 2)
    return event_id


# AC1-H1 (happy): joining a full event stores one Waiting entry at the back
def test_joining_a_full_event_stores_one_entry_at_the_back() -> None:
    repo = FakeWaitlistRepository()
    event_id = full_event(repo)

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(event_id))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "Waiting"
    assert body["position"] == 1
    assert body["queued_at"] == NOW.isoformat()
    assert len(repo.entries) == 1
    # Forbidden side effects: no registration row was created for the caller
    assert not repo.has_active(event_id, ATTENDEE_A)
    listing = client.get(f"/attendee/events/{event_id}").json()
    assert listing["places_remaining"] == 0


# AC1-H3 (happy): an attendee sees only their own entries, with positions
def test_an_attendee_sees_only_their_own_entries_with_positions() -> None:
    repo = FakeWaitlistRepository()
    event_id = full_event(repo)
    with make_waitlist_client(repo, caller_id=ATTENDEE_A) as client:
        assert client.post(join_path(event_id)).status_code == 201

    with make_waitlist_client(repo, caller_id=ATTENDEE_B) as client:
        joined = client.post(join_path(event_id))
        response = client.get("/attendee/waitlist")

    assert joined.status_code == 201
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == joined.json()["id"]
    assert body[0]["position"] == 2
    assert body[0]["status"] == "Waiting"
    # Forbidden side effects: the other attendee's entry is not returned
    assert all(item["id"] != repo.entries[0]["id"] for item in body)


# AC1-N1 (negative): an event with a free place refuses joining
def test_an_event_with_a_free_place_refuses_joining() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "places_available"
    assert repo.entries == []


# AC1-B1, AC8 (boundary): a pending offer makes the event full, so joining a
# one-registered one-offer event succeeds (D6)
def test_a_pending_offer_makes_the_event_joinable() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    add_offer(repo, event_id, str(uuid4()))

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(event_id))

    assert response.status_code == 201
    assert response.json()["status"] == "Waiting"


# AC1-N3 (negative): an attendee who is already registered cannot also wait
def test_a_registered_attendee_cannot_join() -> None:
    repo = FakeWaitlistRepository()
    event_id = full_event(repo)
    add_registration(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "already_registered"
    assert repo.entries == []


@pytest.mark.parametrize("status", [WAITING, OFFERED], ids=["AC1-P1", "AC1-P2"])
# AC1-P1..P2 (partition): an attendee who is already waiting or offered cannot
# rejoin, and their one active entry is kept
def test_an_active_entry_cannot_rejoin(status: str) -> None:
    repo = FakeWaitlistRepository()
    event_id = full_event(repo)
    entry_id = add_waitlist_entry(repo, event_id, ATTENDEE_A, status=status)

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "already_waitlisted"
    assert repo.active_entry(event_id, ATTENDEE_A)["id"] == entry_id
    assert len(repo.entries) == 1


@pytest.mark.parametrize("status", NON_CONFIRMED,
                         ids=[f"AC1-P{k}" for k in range(3, 13)])
# AC1-P3..P12 (partition): each non-Confirmed status hides the event (D8)
def test_a_non_confirmed_event_hides_the_waiting_list(status: str) -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2, status=status)
    fill(repo, event_id, 2)

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(event_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert repo.entries == []


# AC1-N4 (negative): joining an unknown event is not found
def test_joining_an_unknown_event_is_not_found() -> None:
    repo = FakeWaitlistRepository()

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(str(uuid4())))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


@pytest.mark.parametrize(
    "role", ["event_organiser", "event_coordinator", "event_operations_manager"]
)
# AC1-X1 (cross-cutting): only attendees may use the attendee waitlist endpoints
def test_other_roles_cannot_use_the_waitlist_endpoints(role: str) -> None:
    repo = FakeWaitlistRepository()
    event_id = full_event(repo)

    with make_waitlist_client(repo, roles=(role,)) as client:
        joined = client.post(join_path(event_id))
        listed = client.get("/attendee/waitlist")

    assert joined.status_code == 403
    assert listed.status_code == 403
    assert repo.entries == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", f"/attendee/events/{uuid4()}/waitlist"),
        ("get", "/attendee/waitlist"),
    ],
)
# AC1-X1 (cross-cutting): no session is a 401 on every waitlist endpoint
def test_waitlist_endpoints_require_a_session(method: str, path: str) -> None:
    with make_unauthenticated_waitlist_client() as client:
        response = getattr(client, method)(path)

    assert response.status_code == 401


# AC8-H1 (happy): while an offer is pending the event shows no place free, but
# stays listed (D6; SCRUM-21 D8 keeps full events visible)
def test_a_pending_offer_leaves_no_place_visible() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    add_offer(repo, event_id, str(uuid4()))

    with make_waitlist_client(repo) as client:
        single = client.get(f"/attendee/events/{event_id}")
        listed = client.get("/attendee/events")

    assert single.status_code == 200
    assert single.json()["places_remaining"] == 0
    assert listed.status_code == 200
    assert [
        (item["id"], item["places_remaining"]) for item in listed.json()
    ] == [(event_id, 0)]


# AC1-N5 (negative, hotfix): past the cut-off (start - 72h) joining is refused with
# its own code, even though registration is still open, and nothing is stored
def test_joining_after_the_cut_off_is_refused() -> None:
    from datetime import timedelta

    from registration_support import NOW

    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo,
        registration_capacity=2,
        proposed_date_times=[NOW + timedelta(hours=48)],
        registration_closes_at=NOW + timedelta(days=10),
    )
    fill(repo, event_id, 2)

    with make_waitlist_client(repo) as client:
        response = client.post(join_path(event_id))

    assert response.status_code == 409
    assert response.json()["code"] == "waitlist_closed"
    assert repo.entries == []
