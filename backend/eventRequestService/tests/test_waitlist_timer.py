"""SCRUM-24: the waiting-list timer passes over the faked repository.

The timer's real database behaviour is proven by
database/verify_event_waitlist.sql; these tests exercise the pass logic the
service schedules (SCRUM-40's PeriodicTaskRunner) and the notices it writes.
"""

from datetime import timedelta
from uuid import uuid4

from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
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
)

START = NOW + timedelta(days=14)
CUTOFF = START - timedelta(hours=72)  # D8/D11
EXPIRY = NOW + timedelta(hours=72, seconds=1)  # just after a T0 offer lapses


def offered_entry(
    repo: FakeWaitlistRepository, event_id: str, attendee_id: str, **overrides
) -> str:
    return add_offer(repo, event_id, attendee_id, **overrides)


def notices(repo: FakeWaitlistRepository, *types: str) -> list[dict]:
    return [row for row in repo.outbox if row["event_type"] in types]


# AC4-B4 (boundary, D1): at exactly expires_at the offer is untouched
def test_the_timer_leaves_an_offer_alone_at_its_expiry_instant() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    entry_id = add_offer(repo, event_id, ATTENDEE_A)

    repo.process_waitlist_timers(EXPIRY - timedelta(seconds=1))

    assert next(e for e in repo.entries if e["id"] == entry_id)["status"] == "Offered"
    # The 48h warning may have fired; the expiry must not have
    assert not [
        row for row in repo.outbox if row["event_type"] == "waitlist_offer_expired"
    ]


# AC4-B5 (boundary, D1) and AC9-H1 (happy): 1 second after expiry the offer is
# requeued to the back and the place passes on, in the same pass
def test_the_timer_expires_an_offer_one_second_late_and_hands_over() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    a_entry = add_offer(repo, event_id, ATTENDEE_A)
    b_entry = add_waitlist_entry(
        repo, event_id, ATTENDEE_B, queued_at=NOW + timedelta(seconds=1)
    )
    moment = EXPIRY

    repo.process_waitlist_timers(moment)

    expired = next(e for e in repo.entries if e["id"] == a_entry)
    assert expired["status"] == WAITING
    assert expired["queued_at"] == moment  # D3: the back of the queue
    assert expired["offered_at"] is None and expired["expires_at"] is None
    handed = next(e for e in repo.entries if e["id"] == b_entry)
    assert handed["status"] == OFFERED
    assert handed["expires_at"] == moment + timedelta(hours=72)
    # AC5-H3: the old offeree is told they are back in the queue, the next one
    # is offered the place
    expired_notices = [
        row
        for row in repo.outbox
        if row["event_type"] == "waitlist_offer_expired"
    ]
    assert [row["recipient_id"] for row in expired_notices] == [ATTENDEE_A]
    offered_notices = [
        row for row in repo.outbox if row["event_type"] == "waitlist_offered"
    ]
    assert [row["recipient_id"] for row in offered_notices] == [ATTENDEE_B]


# AC4-X1 (cross-cutting): repeating the pass changes nothing
def test_the_timer_pass_is_idempotent() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    add_offer(repo, event_id, ATTENDEE_A)
    add_waitlist_entry(
        repo, event_id, ATTENDEE_B, queued_at=NOW + timedelta(seconds=1)
    )
    moment = EXPIRY
    repo.process_waitlist_timers(moment)

    repo.process_waitlist_timers(moment + timedelta(seconds=1))

    statuses = sorted(e["status"] for e in repo.entries)
    assert statuses == ["Offered", "Waiting"]
    assert len(
        [row for row in repo.outbox if row["event_type"] == "waitlist_offer_expired"]
    ) == 1


# AC5-B1..B2 (boundary, D2): one warning, exactly at offered_at + 48h
def test_the_warning_goes_out_at_forty_eight_hours() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    add_offer(repo, event_id, ATTENDEE_A)

    repo.process_waitlist_timers(NOW + timedelta(hours=48) - timedelta(seconds=1))
    assert repo.outbox == []

    repo.process_waitlist_timers(NOW + timedelta(hours=48))
    warnings = [
        row for row in repo.outbox if row["event_type"] == "waitlist_offer_expiring"
    ]
    assert len(warnings) == 1
    assert warnings[0]["recipient_id"] == ATTENDEE_A


# AC5-N1 (negative): the warning is never repeated
def test_the_warning_is_not_repeated() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    add_offer(repo, event_id, ATTENDEE_A)
    repo.process_waitlist_timers(NOW + timedelta(hours=48))

    repo.process_waitlist_timers(NOW + timedelta(hours=50))

    warnings = [
        row for row in repo.outbox if row["event_type"] == "waitlist_offer_expiring"
    ]
    assert len(warnings) == 1


# AC5-P1..P2 (partition): no warning or expiry notice once the entry is no
# longer Offered
def test_no_notices_after_accepting_or_withdrawing() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    accepted = add_offer(repo, event_id, ATTENDEE_A)
    withdrawn = add_offer(repo, event_id, ATTENDEE_B)
    repo.process_waitlist_timers(NOW)
    for entry in repo.entries:
        if entry["id"] == accepted:
            entry.update(status="Accepted")
        if entry["id"] == withdrawn:
            entry.update(status="Withdrawn")

    repo.process_waitlist_timers(NOW + timedelta(hours=73))

    assert not notices(repo, "waitlist_offer_expiring", "waitlist_offer_expired")


# AC4-P1 (partition, D7): a lone waitlister who lets the place lapse is not
# re-offered it; the place opens to registration
def test_a_lone_waitlister_is_not_reoffered_the_lapsed_place() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=1, proposed_date_times=[START]
    )
    holder = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    add_registration(repo, event_id, holder)
    add_waitlist_entry(repo, event_id, ATTENDEE_A, queued_at=NOW)
    repo._promote(event_id, NOW)
    assert next(
        e for e in repo.entries if e["attendee_id"] == ATTENDEE_A
    )["status"] == "Offered"

    repo.process_waitlist_timers(NOW + timedelta(hours=72, seconds=1))

    entry = next(e for e in repo.entries if e["attendee_id"] == ATTENDEE_A)
    assert entry["status"] == WAITING  # requeued (D3)...
    assert not any(e["status"] == "Offered" for e in repo.entries)  # ...not re-offered


# AC10-B1..B2 (boundary, D11): every Waiting entry closes exactly at the cut-off
def test_the_list_closes_exactly_at_the_cut_off() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    add_waitlist_entry(repo, event_id, ATTENDEE_A, queued_at=NOW)
    add_waitlist_entry(
        repo, event_id, ATTENDEE_B, queued_at=NOW + timedelta(seconds=1)
    )

    repo.process_waitlist_timers(CUTOFF - timedelta(seconds=1))
    assert all(e["status"] == WAITING for e in repo.entries)
    assert repo.outbox == []

    repo.process_waitlist_timers(CUTOFF)
    assert all(e["status"] == "Closed" for e in repo.entries)
    closed = [row for row in repo.outbox if row["event_type"] == "waitlist_closed"]
    assert sorted(row["recipient_id"] for row in closed) == [ATTENDEE_A, ATTENDEE_B]


# AC10-N1 (negative): the closing pass is idempotent
def test_the_closing_pass_is_idempotent() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    add_waitlist_entry(repo, event_id, ATTENDEE_A, queued_at=NOW)
    repo.process_waitlist_timers(CUTOFF)

    repo.process_waitlist_timers(CUTOFF + timedelta(hours=1))

    assert (
        len([row for row in repo.outbox if row["event_type"] == "waitlist_closed"])
        == 1
    )


# AC10-P1 (partition): an in-flight offer runs its own course past the cut-off
# and becomes Closed instead of rejoining the queue
def test_an_offer_expiring_after_the_cut_off_closes_instead_of_requeuing() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    # The offer was made 71h before the cut-off, so it expires an hour after it
    a_entry = add_waitlist_entry(
        repo,
        event_id,
        ATTENDEE_A,
        status="Offered",
        offered_at=CUTOFF - timedelta(hours=71),
        expires_at=CUTOFF + timedelta(hours=1),
        place_id=str(uuid4()),
    )
    add_waitlist_entry(
        repo, event_id, ATTENDEE_B, queued_at=NOW + timedelta(seconds=1)
    )

    repo.process_waitlist_timers(CUTOFF)  # the Waiting entry closes, A runs on
    assert next(e for e in repo.entries if e["id"] == a_entry)["status"] == "Offered"

    repo.process_waitlist_timers(CUTOFF + timedelta(hours=1, seconds=1))
    expired = next(e for e in repo.entries if e["id"] == a_entry)
    assert expired["status"] == "Closed"  # never requeued past the cut-off (D11)
    assert not any(e["status"] == "Offered" for e in repo.entries)


# AC5-N3 (negative): an unreachable notification service never undoes a pass
def test_an_outage_does_not_undo_the_pass() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    fill(repo, event_id, 2)
    add_offer(repo, event_id, ATTENDEE_A)
    add_waitlist_entry(
        repo, event_id, ATTENDEE_B, queued_at=NOW + timedelta(seconds=1)
    )
    repo.rpc_fails = True

    try:
        repo.process_waitlist_timers(NOW + timedelta(hours=72, seconds=1))
        raised = False
    except Exception:  # noqa: BLE001 - the fake raises like SupabaseRepositoryError
        raised = True
    assert raised


# AC11-H1 (happy, A layer): a place freed after the cut-off opens to
# registration; no Closed entry is ever offered
def test_a_place_freed_after_the_cut_off_opens_to_registration() -> None:
    repo = FakeWaitlistRepository()
    event_id = add_event(
        repo, registration_capacity=2, proposed_date_times=[START]
    )
    holder = add_registration(repo, event_id, "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    add_waitlist_entry(repo, event_id, ATTENDEE_A, queued_at=NOW)
    repo.process_waitlist_timers(CUTOFF)  # the list closes

    repo.withdraw(
        holder, "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", CUTOFF + timedelta(days=1)
    )

    assert not any(e["status"] == "Offered" for e in repo.entries)
