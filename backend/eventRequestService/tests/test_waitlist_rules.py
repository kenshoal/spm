"""SCRUM-24: pure waiting-list rules (AC1-B/H, AC2-H/P, AC3-H, AC4-B/H/N/P/X,
AC5-B/H/N/P, AC6-H, AC10-B/N/P)."""

from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest

from app.services.registration_rules import RegistrationNotOpenError
from app.services.waitlist_rules import (
    ACCEPTED,
    CLOSED,
    OFFERED,
    WAITING,
    WITHDRAWN,
    AlreadyRegisteredError,
    AlreadyWaitlistedError,
    NotOfferedError,
    OfferExpiredError,
    PlacesAvailableError,
    check_accept,
    check_join,
    expiry_due,
    may_issue_offer,
    next_recipient,
    offer_deadline,
    requeue,
    waiting_order,
    warning_due,
)

# Test data from docs/testcases/scrum_24_testcases.md ("Test data used below")
T0 = datetime(2030, 1, 10, 9, 0, tzinfo=UTC)  # the offer time
START = datetime(2030, 2, 10, 10, 0, tzinfo=UTC)  # E starts
CUTOFF = START - timedelta(hours=72)  # D8/D11: 2030-02-07T10:00Z
OPENS = datetime(2030, 1, 1, tzinfo=UTC)
CLOSES = datetime(2030, 1, 31, tzinfo=UTC)
ONE_SECOND = timedelta(seconds=1)
TE = T0 + timedelta(hours=72)  # the offer's natural expiry

ATTENDEE_A = "attendee-a"
ATTENDEE_B = "attendee-b"
ATTENDEE_C = "attendee-c"
ATTENDEE_D = "attendee-d"
PLACE_1 = "place-1"
PLACE_2 = "place-2"

_seq = count(1)


def make_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": "event-e",
        "status": "Confirmed",
        "event_name": "Community Dinner",
        "registration_opens_at": OPENS,
        "registration_closes_at": CLOSES,
        "registration_capacity": 2,
    }
    event.update(overrides)
    return event


def make_entry(
    attendee: str,
    *,
    status: str = WAITING,
    queued_at: datetime = T0,
    place_id: str | None = None,
    offered_at: datetime | None = None,
    warned_at: datetime | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": f"entry-{next(_seq)}",
        "seq": next(_seq),
        "event_request_id": "event-e",
        "attendee_id": attendee,
        "status": status,
        "queued_at": queued_at,
        "offered_at": None,
        "expires_at": None,
        "warned_at": warned_at,
        "place_id": place_id,
    }
    if status == OFFERED:
        moment = offered_at if offered_at is not None else T0
        entry["offered_at"] = moment
        entry["expires_at"] = offer_deadline(moment)
        if entry["place_id"] is None:
            entry["place_id"] = PLACE_1
    return entry


def make_place_offer(
    place_id: str, attendee: str, outcome: str
) -> dict[str, str]:
    return {"place_id": place_id, "attendee_id": attendee, "outcome": outcome}


def lapsed(attendee: str, place_id: str = PLACE_1) -> dict[str, str]:
    return make_place_offer(place_id, attendee, "Lapsed")


def queued(attendee: str, offset_seconds: int) -> dict[str, Any]:
    return make_entry(attendee, queued_at=T0 + timedelta(seconds=offset_seconds))


# -- joining -----------------------------------------------------------------

@pytest.mark.parametrize(
    ("now", "refused"),
    [
        (CLOSES - ONE_SECOND, False),
        (CLOSES, True),
        (CLOSES + ONE_SECOND, True),
    ],
    ids=["AC1-B2", "AC1-B3", "AC1-B4"],
)
# AC1-B2..B4 (boundary): joining follows the registration window (D8)
def test_joining_follows_the_registration_window(
    now: datetime, refused: bool
) -> None:
    if refused:
        with pytest.raises(RegistrationNotOpenError):
            check_join(make_event(), now, 2, False, None)
    else:
        check_join(make_event(), now, 2, False, None)


# AC1-B1, AC8-B2 (boundary): a pending offer holds a place, so a full event
# (1 Registered + 1 Offered = capacity) is joinable (D6)
def test_full_event_with_a_pending_offer_is_joinable() -> None:
    check_join(make_event(), T0, 2, False, None)


# AC1-N1 (negative): an event with a free place refuses joining (the API row asserts the 409)
def test_event_with_a_free_place_refuses_joining() -> None:
    with pytest.raises(PlacesAvailableError):
        check_join(make_event(), T0, 1, False, None)


# AC1-N3 (negative): a registered attendee cannot also wait (the API row asserts the 409)
def test_registered_attendee_cannot_join() -> None:
    with pytest.raises(AlreadyRegisteredError):
        check_join(make_event(), T0, 2, True, None)


# AC1-P1..P2 (partition): already waiting or offered cannot rejoin (the API rows assert the 409)
def test_active_waitlist_entry_cannot_rejoin() -> None:
    with pytest.raises(AlreadyWaitlistedError):
        check_join(make_event(), T0, 2, False, make_entry(ATTENDEE_A))


# -- FIFO order and the per-place history (D7) --------------------------------

# AC1-H2 (happy): later joiners queue in join order
def test_later_joiners_queue_in_join_order() -> None:
    entries = [queued(ATTENDEE_A, 0), queued(ATTENDEE_B, 1),
               queued(ATTENDEE_C, 2)]

    assert waiting_order(entries) == entries
    assert next_recipient(entries, PLACE_1, [])["attendee_id"] == ATTENDEE_A


# AC2-P1 (partition): equal queued_at is broken by seq, never by list order
def test_equal_queued_at_is_broken_by_seq() -> None:
    first = make_entry(ATTENDEE_B, queued_at=T0)  # lower seq, later in list
    second = make_entry(ATTENDEE_A, queued_at=T0)
    entries = [second, first]

    assert waiting_order(entries) == [first, second]
    assert next_recipient(entries, PLACE_1, []) is first


# AC2-H2 (happy): two places open, the first two waiting are offered in order
def test_two_places_are_offered_in_order() -> None:
    entries = [queued(ATTENDEE_A, 0), queued(ATTENDEE_B, 1),
               queued(ATTENDEE_C, 2)]
    del entries[0]  # A was offered place 1, so it is no longer Waiting

    assert next_recipient(entries, PLACE_1, [])["attendee_id"] == ATTENDEE_B


# AC3-H2 (happy): a revoked holder is eligible for the same place again (D7)
def test_revoked_holder_is_eligible_for_the_same_place() -> None:
    entries = [queued(ATTENDEE_A, 0), queued(ATTENDEE_B, 1)]
    history = [make_place_offer(PLACE_1, ATTENDEE_A, "Revoked")]

    assert next_recipient(entries, PLACE_1, history)["attendee_id"] == ATTENDEE_A


# AC6-H2 (happy): the next place skips a withdrawn attendee
def test_next_place_skips_a_withdrawn_attendee() -> None:
    entries = [
        queued(ATTENDEE_A, 0),
        make_entry(ATTENDEE_B, status=WITHDRAWN, queued_at=T0 + ONE_SECOND),
        queued(ATTENDEE_C, 2),
    ]

    assert next_recipient(entries, PLACE_1, [])["attendee_id"] == ATTENDEE_A
    del entries[0]  # A was offered place 1

    assert next_recipient(entries, PLACE_1, [])["attendee_id"] == ATTENDEE_C


# AC4-P2 (partition): the place goes to everyone once, then is released (D7)
def test_place_is_released_once_everyone_has_had_it() -> None:
    entries = [queued(ATTENDEE_A, 0), queued(ATTENDEE_B, 1)]

    assert next_recipient(entries, PLACE_1, [lapsed(ATTENDEE_A)])[
        "attendee_id"
    ] == ATTENDEE_B
    assert next_recipient(
        entries, PLACE_1, [lapsed(ATTENDEE_A), lapsed(ATTENDEE_B)]
    ) is None


# AC4-P4 (partition): no queue-jumping while someone has not had the place
def test_place_is_not_released_while_someone_has_not_had_it() -> None:
    entries = [queued(ATTENDEE_B, 1), queued(ATTENDEE_C, 2)]

    assert next_recipient(entries, PLACE_1, [lapsed(ATTENDEE_A)])[
        "attendee_id"
    ] == ATTENDEE_B
    assert next_recipient(
        entries, PLACE_1, [lapsed(ATTENDEE_A), lapsed(ATTENDEE_B)]
    )["attendee_id"] == ATTENDEE_C


# AC4-P3 (partition): letting one place lapse does not bar a new place
def test_a_new_place_ignores_another_place_history() -> None:
    entries = [queued(ATTENDEE_A, 0), queued(ATTENDEE_B, 1)]

    assert next_recipient(entries, PLACE_2, [lapsed(ATTENDEE_A, PLACE_1)])[
        "attendee_id"
    ] == ATTENDEE_A


# AC2-N1 (negative): only Waiting entries are ever recipients (the API row asserts no offer)
def test_non_waiting_entries_are_skipped() -> None:
    entries = [
        make_entry(ATTENDEE_A, status=WITHDRAWN),
        make_entry(ATTENDEE_B, status=ACCEPTED),
        make_entry(ATTENDEE_C, status=CLOSED),
        queued(ATTENDEE_D, 0),
    ]

    assert next_recipient(entries, PLACE_1, [])["attendee_id"] == ATTENDEE_D


# -- the acceptance window (D1) -----------------------------------------------

@pytest.mark.parametrize(
    ("now", "refused"),
    [
        (TE - ONE_SECOND, False),
        (TE, False),
        (TE + ONE_SECOND, True),
    ],
    ids=["AC4-B1", "AC4-B2", "AC4-B3"],
)
# AC4-B1..B3 (boundary): the 72h window is inclusive (D1)
def test_the_acceptance_window_is_inclusive(now: datetime, refused: bool) -> None:
    entry = make_entry(ATTENDEE_A, status=OFFERED)
    if refused:
        with pytest.raises(OfferExpiredError):
            check_accept(entry, now)
    else:
        check_accept(entry, now)


# AC4-N3 (negative): only an Offered entry can be accepted (the API row asserts the 409)
@pytest.mark.parametrize("status", [WAITING, ACCEPTED, WITHDRAWN, CLOSED])
def test_only_an_offered_entry_can_be_accepted(status: str) -> None:
    with pytest.raises(NotOfferedError):
        check_accept(make_entry(ATTENDEE_A, status=status), T0)


# -- the timer's predicates (D1, D2) ------------------------------------------

# AC4-B4..B5 (boundary): the timer expires only after the instant (D1)
def test_expiry_runs_only_after_the_instant() -> None:
    entry = make_entry(ATTENDEE_A, status=OFFERED)

    assert expiry_due(entry, TE) is False
    assert expiry_due(entry, TE + ONE_SECOND) is True


# AC4-H2 (happy): an expired offeree goes behind everyone waiting (D3)
def test_an_expired_offeree_goes_to_the_back() -> None:
    waiting_c = queued(ATTENDEE_C, 2)  # B was offered the place meanwhile
    requeued = requeue(make_entry(ATTENDEE_A, status=OFFERED), TE)

    assert requeued["status"] == WAITING
    assert requeued["queued_at"] == TE
    assert requeued["offered_at"] is None
    assert requeued["expires_at"] is None
    assert requeued["warned_at"] is None
    assert requeued["place_id"] is None
    assert waiting_order([requeued, waiting_c]) == [waiting_c, requeued]


# AC4-X1 (cross-cutting): a requeued entry cannot expire or warn twice
def test_a_requeued_entry_is_inert_for_the_old_offer() -> None:
    requeued_entry = requeue(
        make_entry(ATTENDEE_A, status=OFFERED, warned_at=T0), TE
    )

    assert expiry_due(requeued_entry, TE + ONE_SECOND) is False
    assert warning_due(requeued_entry, TE + timedelta(hours=48)) is False


# AC5-B1..B2 (boundary): the warning goes out exactly at T0 + 48h (D2)
def test_the_warning_goes_out_exactly_48h_after_the_offer() -> None:
    entry = make_entry(ATTENDEE_A, status=OFFERED)
    warn_at = T0 + timedelta(hours=48)

    assert warning_due(entry, warn_at - ONE_SECOND) is False
    assert warning_due(entry, warn_at) is True


# AC5-N1 (negative): the warning is not repeated
def test_the_warning_is_not_repeated() -> None:
    entry = make_entry(ATTENDEE_A, status=OFFERED, warned_at=T0)

    assert warning_due(entry, T0 + timedelta(hours=50)) is False


@pytest.mark.parametrize(
    "status",
    [ACCEPTED, WITHDRAWN, WAITING],
    ids=["AC5-P1", "AC5-P2", "AC5-P3"],
)
# AC5-P1..P3 (partition): no warning or expiry notice after accepting,
# withdrawing or a revoke (a revoked holder is back to Waiting)
def test_no_warning_or_expiry_for_a_non_offered_entry(status: str) -> None:
    entry = make_entry(ATTENDEE_A, status=status)

    assert warning_due(entry, T0 + timedelta(hours=48)) is False
    assert expiry_due(entry, TE + ONE_SECOND) is False


# AC5-H3 (happy): expiry frees the place for the next eligible attendee
def test_expiry_frees_the_place_for_the_next_recipient() -> None:
    offered = make_entry(ATTENDEE_A, status=OFFERED)
    waiting_b = queued(ATTENDEE_B, 1)

    assert expiry_due(offered, TE + ONE_SECOND) is True
    assert next_recipient([waiting_b], PLACE_1, [lapsed(ATTENDEE_A)])[
        "attendee_id"
    ] == ATTENDEE_B


# -- the #116 cut-off (D8, D11, D12) ------------------------------------------

@pytest.mark.parametrize(
    ("now", "allowed"),
    [
        (CUTOFF - ONE_SECOND, True),
        (CUTOFF, False),
    ],
    ids=["AC4-B8", "AC4-B9"],
)
# AC4-B8..B9 (boundary): new offers stop at the strict #116 cut-off (D8)
def test_new_offers_stop_at_the_strict_cut_off(
    now: datetime, allowed: bool
) -> None:
    assert may_issue_offer(now, START) is allowed


# AC4-N6 (negative): an offer expiring after the cut-off is not passed on
def test_an_offer_expiring_after_the_cut_off_is_not_passed_on() -> None:
    offered_at = CUTOFF - timedelta(seconds=10)
    offered = make_entry(
        ATTENDEE_A, status=OFFERED, offered_at=offered_at
    )
    expires = offer_deadline(offered_at)

    assert expiry_due(offered, expires + ONE_SECOND) is True
    assert may_issue_offer(expires + ONE_SECOND, START) is False


@pytest.mark.parametrize(
    ("now", "allowed"),
    [
        (CUTOFF - ONE_SECOND, True),
        (CUTOFF, False),
    ],
    ids=["AC10-B1", "AC10-B2"],
)
# AC10-B1..B2 (boundary): the list closes exactly at the cut-off (D11)
def test_the_list_closes_exactly_at_the_cut_off(
    now: datetime, allowed: bool
) -> None:
    # D11: the closing condition is exactly "no new offer can be issued".
    assert may_issue_offer(now, START) is allowed


# AC10-P1 (partition): an in-flight offer runs its own course past the cut-off
def test_an_in_flight_offer_runs_its_own_course() -> None:
    # Offered 10s before the cut-off, so it expires 72h - 10s after it.
    offered_at = CUTOFF - ONE_SECOND * 10
    offered = make_entry(ATTENDEE_A, status=OFFERED, offered_at=offered_at)

    # The cut-off pass leaves the in-flight offer untouched...
    assert expiry_due(offered, CUTOFF) is False
    # ...and its own expiry closes it instead of requeueing it: past the
    # cut-off a new offer could never be issued, so back of the queue is moot.
    assert expiry_due(offered, offer_deadline(offered_at) + ONE_SECOND) is True
    assert may_issue_offer(offer_deadline(offered_at) + ONE_SECOND, START) is False


# AC10-N1 (negative): a Closed entry is inert
def test_a_closed_entry_is_inert() -> None:
    closed = make_entry(ATTENDEE_A, status=CLOSED)

    assert expiry_due(closed, TE + ONE_SECOND) is False
    assert warning_due(closed, T0 + timedelta(hours=48)) is False
    assert next_recipient([closed], PLACE_1, []) is None
