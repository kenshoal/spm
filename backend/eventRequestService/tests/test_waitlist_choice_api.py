"""SCRUM-24: the assigned Coordinator choosing an offer's recipient (AC3, D9).

The repository is faked (see waitlist_support.py); the real database function
is proven by database/verify_event_waitlist.sql.
"""

from datetime import timedelta

from registration_support import ATTENDEE_A, ATTENDEE_B, NOW, add_event, fill
from waitlist_support import (
    WAITING,
    FakeWaitlistRepository,
    add_offer,
    add_waitlist_entry,
    make_waitlist_client,
)

from app.clock import get_now

COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
CHOSEN = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
OFFER_WINDOW = timedelta(hours=72)  # D1


def choice_path(event_id: str, entry_id: str) -> str:
    return f"/event-requests/{event_id}/waitlist/{entry_id}/offer"


def full_event_with_offer(
    repo: FakeWaitlistRepository, *waiters: str
) -> tuple[str, str, dict[str, str]]:
    """A full event, one open place offered to A, the given attendees waiting."""
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 2)
    repo.coordinators[event_id] = COORDINATOR
    offered = add_offer(repo, event_id, ATTENDEE_A)
    entries = {}
    for index, attendee in enumerate(waiters):
        entries[attendee] = add_waitlist_entry(
            repo, event_id, attendee, queued_at=NOW + timedelta(seconds=index)
        )
    return event_id, offered, entries


def coordinator_client(repo: FakeWaitlistRepository):
    return make_waitlist_client(
        repo, caller_id=COORDINATOR, roles=("event_coordinator",)
    )


# AC3-H1 and AC5-H2 (happy): the Coordinator chooses the recipient; the
# automatic offer is revoked, its holder keeps their position, and both are told
def test_the_coordinator_chooses_the_recipient_and_the_offer_is_revoked() -> None:
    repo = FakeWaitlistRepository()
    event_id, offered, entries = full_event_with_offer(
        repo, ATTENDEE_B, CHOSEN
    )
    holder = next(e for e in repo.entries if e["id"] == offered)
    moment = NOW + timedelta(hours=1)

    with coordinator_client(repo) as client:
        client.app.dependency_overrides[get_now] = lambda: moment
        response = client.post(choice_path(event_id, entries[CHOSEN]))

    assert response.status_code == 200
    chosen = next(e for e in repo.entries if e["id"] == entries[CHOSEN])
    assert chosen["status"] == "Offered"
    assert chosen["offered_at"] == moment
    assert chosen["expires_at"] == moment + OFFER_WINDOW
    # D9: the revoked holder keeps their queued_at, so their position
    assert holder["status"] == WAITING
    assert holder["queued_at"] == NOW
    assert holder["place_id"] is None
    with make_waitlist_client(repo, caller_id=ATTENDEE_A) as client:
        assert client.get("/attendee/waitlist").json()[0]["position"] == 1
    with make_waitlist_client(repo, caller_id=ATTENDEE_B) as client:
        assert client.get("/attendee/waitlist").json()[0]["position"] == 2
    revoked = [
        row for row in repo.outbox if row["event_type"] == "waitlist_offer_revoked"
    ]
    assert [row["recipient_id"] for row in revoked] == [ATTENDEE_A]
    offered_notices = [
        row
        for row in repo.outbox
        if row["event_type"] == "waitlist_offered"
        and row["recipient_id"] == CHOSEN
    ]
    assert len(offered_notices) == 1
    # AC5-P3 (partition): the revoked window warns and expires for nobody
    repo.process_waitlist_timers(NOW + timedelta(hours=73))
    assert not [
        row
        for row in repo.outbox
        if row["event_type"] in ("waitlist_offer_expiring", "waitlist_offer_expired")
        and row["recipient_id"] == ATTENDEE_A
    ]


# AC3-N1 (negative): only the event's assigned Coordinator may choose
def test_only_the_assigned_coordinator_may_choose() -> None:
    repo = FakeWaitlistRepository()
    event_id, _offered, entries = full_event_with_offer(repo, ATTENDEE_B)

    with make_waitlist_client(repo, caller_id="k2", roles=("event_coordinator",)) as client:
        wrong_coordinator = client.post(choice_path(event_id, entries[ATTENDEE_B]))
    with make_waitlist_client(
        repo, caller_id="org-1", roles=("event_organiser",)
    ) as client:
        organiser = client.post(choice_path(event_id, entries[ATTENDEE_B]))
    with make_waitlist_client(repo) as client:
        attendee = client.post(choice_path(event_id, entries[ATTENDEE_B]))

    assert wrong_coordinator.status_code == 403
    assert organiser.status_code == 403
    assert attendee.status_code == 403
    assert next(e for e in repo.entries if e["id"] == entries[ATTENDEE_B])[
        "status"
    ] == WAITING


# AC3-P1..P4 (partition): the chosen entry must be Waiting in this event
def test_the_chosen_entry_must_be_waiting_in_this_event() -> None:
    repo = FakeWaitlistRepository()
    event_id, offered, entries = full_event_with_offer(repo, ATTENDEE_B)
    next(e for e in repo.entries if e["id"] == offered)["status"] = "Withdrawn"
    accepted = add_offer(repo, event_id, CHOSEN)
    next(e for e in repo.entries if e["id"] == accepted)["status"] = "Accepted"

    with coordinator_client(repo) as client:
        revoked_choice = client.post(choice_path(event_id, offered))
        accepted_choice = client.post(choice_path(event_id, accepted))
        other_event = add_event(repo, registration_capacity=2)
        fill(repo, other_event, 2)
        repo.coordinators[other_event] = COORDINATOR
        stranger = add_offer(repo, other_event, ATTENDEE_B)
        cross = client.post(choice_path(event_id, stranger))

    assert revoked_choice.status_code == 409
    assert revoked_choice.json()["code"] == "not_waiting"
    assert accepted_choice.status_code == 409
    assert accepted_choice.json()["code"] == "not_waiting"
    assert cross.status_code == 404
    assert next(e for e in repo.entries if e["id"] == entries[ATTENDEE_B])[
        "status"
    ] == WAITING


# AC3-N2 (negative): no open place, so there is nothing to assign
def test_choosing_without_an_open_place_is_refused() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 2)
    repo.coordinators[event_id] = COORDINATOR
    entry = add_waitlist_entry(repo, event_id, ATTENDEE_B, queued_at=NOW)

    with coordinator_client(repo) as client:
        response = client.post(choice_path(event_id, entry))

    assert response.status_code == 409
    assert response.json()["code"] == "no_open_place"
    assert next(e for e in repo.entries if e["id"] == entry)["status"] == WAITING
    assert repo.outbox == []


# AC2-N1 (negative): when the database refuses a choice because the 72 hours would run
# past registration close or the event start, the Coordinator gets a clear 409 and the
# offer in flight is untouched
def test_a_choice_that_would_run_past_registration_close_is_refused() -> None:
    from app.repositories.registration_repository import RegistrationRpcError

    repo = FakeWaitlistRepository()
    event_id, offered, entries = full_event_with_offer(repo, ATTENDEE_B)

    def refuse(*args: object, **kwargs: object) -> None:
        raise RegistrationRpcError("offer window", "P0004", "offer window")

    repo.choose_waitlist_recipient = refuse  # type: ignore[method-assign]
    with coordinator_client(repo) as client:
        response = client.post(choice_path(event_id, entries[ATTENDEE_B]))

    assert response.status_code == 409
    assert response.json()["code"] == "offer_window_closed"
    assert next(e for e in repo.entries if e["id"] == offered)["status"] == "Offered"
    assert next(e for e in repo.entries if e["id"] == entries[ATTENDEE_B])["status"] == WAITING
