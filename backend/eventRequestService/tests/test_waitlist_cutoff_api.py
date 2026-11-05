"""SCRUM-24: what attendees and Coordinators see after the timer runs.

The pass logic is in test_waitlist_timer.py; these rows check the HTTP
outcome of a released place (AC9-H2) and of the cut-off (AC10-H1, AC11-N1).
The repository is faked (see waitlist_support.py); the real database
functions are proven by database/verify_event_waitlist.sql.
"""

from datetime import timedelta

from registration_support import ATTENDEE_A, ATTENDEE_B, NOW, add_event, fill
from waitlist_support import (
    OFFERED,
    FakeWaitlistRepository,
    add_offer,
    add_waitlist_entry,
    make_waitlist_client,
)

ATTENDEE_D = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
COORDINATOR = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
START = NOW + timedelta(days=14)
CUTOFF = START - timedelta(hours=72)  # D8/D11
EXPIRY = NOW + timedelta(hours=72, seconds=1)  # just after a T0 offer lapses


def closed_event(repo: FakeWaitlistRepository) -> tuple[str, dict[str, str]]:
    """A full event whose waiting list the cut-off pass has just closed."""
    event_id = add_event(repo, registration_capacity=2, proposed_date_times=[START])
    fill(repo, event_id, 2)
    repo.coordinators[event_id] = COORDINATOR
    entries = {
        ATTENDEE_A: add_waitlist_entry(repo, event_id, ATTENDEE_A, queued_at=NOW),
        ATTENDEE_B: add_waitlist_entry(
            repo, event_id, ATTENDEE_B, queued_at=NOW + timedelta(seconds=1)
        ),
    }
    repo.process_waitlist_timers(CUTOFF)
    return event_id, entries


# AC9-H2 (happy): once everyone has had a place it is released, and a direct
# registration can take it
def test_a_released_place_can_be_taken_by_direct_registration() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(repo, registration_capacity=2)
    fill(repo, event_id, 1)
    add_offer(repo, event_id, ATTENDEE_A)  # the only waitlister holds the place
    repo.process_waitlist_timers(EXPIRY)  # A lets it lapse; nobody else (D7)
    assert not any(e["status"] == OFFERED for e in repo.entries)

    with make_waitlist_client(repo, caller_id=ATTENDEE_D) as client:
        response = client.post(f"/attendee/events/{event_id}/registrations")

    assert response.status_code == 201
    assert response.json()["status"] == "Registered"


# AC10-H1 (happy): the cut-off closes every waiting entry, tells each attendee
# once, and their listing shows it Closed with no position
def test_the_cut_off_closes_every_entry_and_the_listing_shows_it() -> None:
    repo = FakeWaitlistRepository()
    _event_id, entries = closed_event(repo)

    closed = [row for row in repo.outbox if row["event_type"] == "waitlist_closed"]
    assert sorted(row["recipient_id"] for row in closed) == [ATTENDEE_A, ATTENDEE_B]
    for attendee, entry_id in entries.items():
        with make_waitlist_client(repo, caller_id=attendee) as client:
            listing = client.get("/attendee/waitlist")
        assert listing.status_code == 200
        assert [
            (item["id"], item["status"], item["position"]) for item in listing.json()
        ] == [(entry_id, "Closed", None)]
    # Forbidden side effect: no offer is made at the cut-off
    assert not any(e["status"] == OFFERED for e in repo.entries)


# AC11-N1 (negative): a Closed entry cannot be offered or accepted
def test_a_closed_entry_cannot_be_offered_or_accepted() -> None:
    repo = FakeWaitlistRepository()
    event_id, entries = closed_event(repo)
    a_entry = entries[ATTENDEE_A]
    notices_before = len(repo.outbox)

    with make_waitlist_client(
        repo, caller_id=COORDINATOR, roles=("event_coordinator",)
    ) as client:
        chosen = client.post(f"/event-requests/{event_id}/waitlist/{a_entry}/offer")
    with make_waitlist_client(repo, caller_id=ATTENDEE_A) as client:
        accepted = client.post(f"/attendee/waitlist/{a_entry}/acceptance")

    assert chosen.status_code == 409
    assert chosen.json()["code"] == "not_waiting"
    assert accepted.status_code == 404
    # Nothing changes
    assert next(e for e in repo.entries if e["id"] == a_entry)["status"] == "Closed"
    assert len(repo.outbox) == notices_before
    assert len(repo.registrations) == 2
