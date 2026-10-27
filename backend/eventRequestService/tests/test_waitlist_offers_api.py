"""SCRUM-24: accepting, withdrawing and the hand-over of offers over HTTP.

The repository is faked (see waitlist_support.py); the real database function
is proven by database/verify_event_waitlist.sql.
"""

from datetime import timedelta
from uuid import uuid4

from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
    NOW,
    add_event,
    fill,
)
from waitlist_support import (
    ATTENDEE_C,
    WAITING,
    FakeWaitlistRepository,
    add_offer,
    add_waitlist_entry,
    make_waitlist_client,
)

from app.clock import get_now

OFFER_WINDOW = timedelta(hours=72)  # D1


def acceptance_path(entry_id: str) -> str:
    return f"/attendee/waitlist/{entry_id}/acceptance"


def withdrawal_path(entry_id: str) -> str:
    return f"/attendee/waitlist/{entry_id}/withdrawal"


def full_event_with_queue(
    repo: FakeWaitlistRepository, *attendees: str
) -> dict[str, str]:
    """A full event with the given attendees waiting, one second apart."""
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 2)
    entries = {}
    for index, attendee in enumerate(attendees):
        entries[attendee] = add_waitlist_entry(
            repo, event_id, attendee, queued_at=NOW + timedelta(seconds=index)
        )
    return event_id, entries


# AC2-H1 (happy): withdrawing a registration offers the place to the earliest
# waiting attendee, in the same transaction, and nothing looks free
def test_a_withdrawal_offers_the_place_to_the_earliest_attendee() -> None:
    repo = FakeWaitlistRepository()
    event_id, entries = full_event_with_queue(repo, ATTENDEE_A, ATTENDEE_B, ATTENDEE_C)
    holder = repo.registrations[0]

    with make_waitlist_client(repo, caller_id=holder["attendee_id"]) as client:
        withdrawn = client.post(f"/attendee/registrations/{holder['id']}/withdrawal")
        offered = client.get("/attendee/waitlist")

    assert withdrawn.status_code == 200
    body = offered.json()
    mine = next(item for item in body if item["id"] == entries[ATTENDEE_A])
    assert mine["status"] == "Offered"
    assert mine["offered_at"] == NOW.isoformat()
    assert mine["expires_at"] == (NOW + OFFER_WINDOW).isoformat()
    assert mine["position"] == 1
    # Forbidden side effects: the place is held, so nothing looks free, and the
    # queue behind keeps its order
    assert client.get(f"/attendee/events/{event_id}").json()["places_remaining"] == 0


# AC4-H1 (happy): accepting within the window registers the attendee
def test_accepting_within_the_window_registers_the_attendee() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo) as client:
        response = client.post(acceptance_path(entry_id))

    assert response.status_code == 200
    body = response.json()
    assert body["entry"]["status"] == "Accepted"
    assert body["registration"]["status"] == "Registered"
    assert repo.has_active(event_id, ATTENDEE_A)
    # Forbidden side effects: the hold became the registration, so the event
    # still shows no place free
    assert client.get(f"/attendee/events/{event_id}").json()["places_remaining"] == 0


def test_accepting_just_inside_the_window_succeeds() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    # AC4-B1 (boundary, D1): accepting 1 second before the window ends succeeds
    with make_waitlist_client(repo) as client:
        client.app.dependency_overrides[get_now] = lambda: NOW + OFFER_WINDOW - timedelta(
            seconds=1
        )
        assert client.post(acceptance_path(entry_id)).status_code == 200


# AC4-B2 (boundary, D1): accepting exactly at expires_at still succeeds
def test_accepting_exactly_at_the_window_end_succeeds() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo) as client:
        client.app.dependency_overrides[get_now] = lambda: NOW + OFFER_WINDOW
        response = client.post(acceptance_path(entry_id))

    assert response.status_code == 200


# AC4-B3 (boundary, D1): 1 second after the window the offer has expired, and
# nothing was written even though the timer has not run
def test_accepting_just_after_the_window_is_refused() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo) as client:
        client.app.dependency_overrides[get_now] = lambda: NOW + OFFER_WINDOW + timedelta(
            seconds=1
        )
        response = client.post(acceptance_path(entry_id))

    assert response.status_code == 409
    assert response.json()["code"] == "offer_expired"
    assert next(
        e for e in repo.entries if e["id"] == entry_id
    )["status"] == "Offered"
    assert not repo.has_active(event_id, ATTENDEE_A)


# AC4-N2 (negative): someone else's or an unknown offer is the same "not found"
def test_accepting_someone_elses_or_unknown_entry_is_not_found() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo, caller_id=ATTENDEE_B) as client:
        theirs = client.post(acceptance_path(entry_id))
        unknown = client.post(acceptance_path(str(uuid4())))

    assert theirs.status_code == 404
    assert unknown.status_code == 404
    assert next(e for e in repo.entries if e["id"] == entry_id)["status"] == "Offered"


# AC4-N3 (negative): accepting twice is refused, and the one registration stays
def test_accepting_twice_is_refused() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo) as client:
        assert client.post(acceptance_path(entry_id)).status_code == 200
        again = client.post(acceptance_path(entry_id))

    assert again.status_code == 409
    assert again.json()["code"] == "not_offered"
    assert (
        sum(
            1
            for r in repo.registrations
            if r["event_request_id"] == event_id and r["attendee_id"] == ATTENDEE_A
        )
        == 1
    )


# AC4-N4 (negative): a cancelled event hides the waiting list, so its offer
# cannot be accepted (D8)
def test_an_offer_on_a_cancelled_event_cannot_be_accepted() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)
    repo.events[event_id]["status"] = "Cancelled"

    with make_waitlist_client(repo) as client:
        response = client.post(acceptance_path(entry_id))

    assert response.status_code == 404
    assert not repo.has_active(event_id, ATTENDEE_A)


# AC4-N5 (negative): a Supabase outage is a 502 and undoes nothing
def test_an_outage_on_accept_is_a_502_and_writes_nothing() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)
    repo.rpc_fails = True

    with make_waitlist_client(repo) as client:
        response = client.post(acceptance_path(entry_id))

    assert response.status_code == 502
    assert next(e for e in repo.entries if e["id"] == entry_id)["status"] == "Offered"
    assert not repo.has_active(event_id, ATTENDEE_A)


# AC6-H1 (happy): a waiting attendee withdraws; everyone behind moves up
def test_a_waiting_attendee_withdraws_and_the_queue_closes_the_gap() -> None:
    repo = FakeWaitlistRepository()
    _event_id, entries = full_event_with_queue(
        repo, ATTENDEE_A, ATTENDEE_B, ATTENDEE_C, "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    )
    b_entry = entries[ATTENDEE_B]

    with make_waitlist_client(repo, caller_id=ATTENDEE_B) as client:
        response = client.post(withdrawal_path(b_entry))
        listing = client.get("/attendee/waitlist")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Withdrawn"
    assert body["withdrawn_at"] == NOW.isoformat()
    assert [item["position"] for item in listing.json()] == [2]
    with make_waitlist_client(repo, caller_id=ATTENDEE_C) as behind:
        c_entry = behind.get("/attendee/waitlist").json()[0]
        assert c_entry["id"] == entries[ATTENDEE_C]
        assert c_entry["position"] == 2


# AC6-N1 (negative): withdrawing twice is refused
def test_withdrawing_twice_is_refused() -> None:
    repo = FakeWaitlistRepository()
    _event_id, entries = full_event_with_queue(repo, ATTENDEE_A, ATTENDEE_B)

    with make_waitlist_client(repo, caller_id=ATTENDEE_B) as client:
        assert client.post(withdrawal_path(entries[ATTENDEE_B])).status_code == 200
        again = client.post(withdrawal_path(entries[ATTENDEE_B]))

    assert again.status_code == 409
    assert again.json()["code"] == "already_withdrawn"


# AC6-N2 (negative): someone else's or an unknown entry is the same "not found"
def test_withdrawing_someone_elses_or_unknown_entry_is_not_found() -> None:
    repo = FakeWaitlistRepository()
    _event_id, entries = full_event_with_queue(repo, ATTENDEE_A, ATTENDEE_B)

    with make_waitlist_client(repo) as client:
        theirs = client.post(withdrawal_path(entries[ATTENDEE_B]))
        unknown = client.post(withdrawal_path(str(uuid4())))

    assert theirs.status_code == 404
    assert unknown.status_code == 404
    assert next(
        e for e in repo.entries if e["id"] == entries[ATTENDEE_B]
    )["status"] == WAITING


# AC7-H1 (happy): withdrawing with an offer passes it on with a fresh window
def test_withdrawing_with_an_offer_passes_it_on() -> None:
    repo = FakeWaitlistRepository()
    event_id, entries = full_event_with_queue(repo, ATTENDEE_A, ATTENDEE_B, ATTENDEE_C)
    a_entry = add_offer(repo, event_id, ATTENDEE_A, queued_at=NOW)

    with make_waitlist_client(repo) as client:
        client.app.dependency_overrides[get_now] = lambda: NOW + timedelta(hours=10)
        response = client.post(withdrawal_path(a_entry))
        listed = client.get("/attendee/waitlist")

    assert response.status_code == 200
    assert response.json()["status"] == "Withdrawn"
    assert listed.json() == []  # the caller's offer is gone from their list
    b_entry = next(e for e in repo.entries if e["id"] == entries[ATTENDEE_B])
    assert b_entry["status"] == "Offered"
    assert b_entry["offered_at"] == NOW + timedelta(hours=10)
    assert b_entry["expires_at"] == NOW + timedelta(hours=10) + OFFER_WINDOW


# AC7-N1 (negative): nobody else waiting, so the place is simply released
def test_withdrawing_a_lone_offer_releases_the_place() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo) as client:
        response = client.post(withdrawal_path(entry_id))
        remaining = client.get(f"/attendee/events/{event_id}").json()

    assert response.status_code == 200
    assert remaining["places_remaining"] == 1
    assert not any(e["status"] == "Offered" for e in repo.entries)


# AC7-N2 (negative): withdrawing after accepting is not a waiting-list action
def test_withdrawing_an_accepted_entry_is_refused() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    with make_waitlist_client(repo) as client:
        assert client.post(acceptance_path(entry_id)).status_code == 200
        response = client.post(withdrawal_path(entry_id))

    assert response.status_code == 409
    assert response.json()["code"] == "not_offered"
    assert repo.has_active(event_id, ATTENDEE_A)
