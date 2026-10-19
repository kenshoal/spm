"""Unit tests for the SCRUM-13 row-availability rule in app/availability.py.

``row_available`` answers: how many units of this one catalogue row are free
for the whole hold window of a new event (decision D4)? It reuses SCRUM-10's
hold_window, needs_transfer and committed_peak, so these cases pin that the
reserve path counts exactly as the availability check does.

Test-case IDs trace to docs/testcases/scrum_13_testcases.md. All dates are
October 2026; the event venue is Search Big Hall (building "Search Wing").
"""

from datetime import date

import pytest

from app.availability import (
    EquipmentRow,
    RequestedItem,
    Reservation,
    Venue,
    check_availability,
    row_available,
)


def oct_(day: int) -> date:
    return date(2026, 10, day)


FRI9, SAT10, SUN11, MON12, TUE13, WED14, THU15, FRI16 = (
    oct_(day) for day in range(9, 17)
)

BIG = Venue("v-big", "Search Big Hall", "Search Wing")
SMALL = Venue("v-small", "Search Small Room", "Search Wing")
CLOSED = Venue("v-closed", "Search Closed Hall", "Search Wing")
HARBOUR = Venue("v-harbour", "Harbour Room", "Harbour Block")
VENUES = [BIG, SMALL, CLOSED, HARBOUR]

P10 = EquipmentRow("p10", "Projector", 10, "Store Room B")
PX = EquipmentRow("px", "Projector", 6, "Store Room C")
PH10 = EquipmentRow("ph10", "Projector", 10, "Harbour Room")


def R(row: EquipmentRow, qty: int, collect: date, ret: date) -> Reservation:
    return Reservation(row.id, qty, collect, ret)


def free(
    row: EquipmentRow,
    reservations: list[Reservation],
    start: date,
    end: date | None = None,
) -> int:
    return row_available(
        row=row,
        reservations=reservations,
        start_date=start,
        end_date=end or start,
        event_venue=BIG,
        venues=VENUES,
    )


# --- AC3 ---------------------------------------------------------------------

# Event A on Mon 12 holds every projector in P10 (collected Sun 11).
A_HOLDS_ALL = [R(P10, 10, SUN11, MON12)]


# AC3-P1 (partition): a reservation outside the hold window is ignored
def test_reservation_outside_hold_is_ignored() -> None:
    late = [R(P10, 10, oct_(30), oct_(31))]

    assert free(P10, late, WED14) == 10


# AC3-P2 (partition): a reservation on another row of the same type is ignored
def test_reservation_on_another_row_is_ignored() -> None:
    other_row = [R(PX, 6, TUE13, WED14)]

    assert free(P10, other_row, WED14) == 10


# AC3-P4 (partition): busiest day counts, not the sum of reservations that never overlap
def test_busiest_day_not_sum() -> None:
    apart = [R(P10, 5, MON12, MON12), R(P10, 5, FRI16, FRI16)]

    assert free(P10, apart, MON12, FRI16) == 5


# AC3-B1, AC3-B2, AC3-B3, AC3-B4 (boundary): D-1 collection and Return Day + 1 edges
@pytest.mark.parametrize(
    ("event_day", "expected"),
    [
        (TUE13, 0),  # hold Mon 12 -> Tue 13: collects on A's return day
        (WED14, 10),  # hold Tue 13 -> Wed 14: Return Day + 1, first free day
        (SUN11, 0),  # hold Sat 10 -> Sun 11: A's collection day
        (SAT10, 10),  # hold Fri 9 -> Sat 10: ends before A collects
    ],
    ids=["AC3-B1", "AC3-B2", "AC3-B3", "AC3-B4"],
)
def test_hold_window_edges(event_day: date, expected: int) -> None:
    assert free(P10, A_HOLDS_ALL, event_day) == expected


# AC3-B5, AC3-B6 (boundary): a row in another building collects one transfer day earlier
@pytest.mark.parametrize(
    ("event_day", "expected"),
    [
        (WED14, 0),  # hold Mon 12 -> Wed 14 overlaps A's return on Mon 12
        (THU15, 10),  # hold Tue 13 -> Thu 15 is clear
    ],
    ids=["AC3-B5", "AC3-B6"],
)
def test_transfer_day_edges(event_day: date, expected: int) -> None:
    a_holds_harbour = [R(PH10, 10, SAT10, MON12)]

    assert free(PH10, a_holds_harbour, event_day) == expected


# --- AC5 ---------------------------------------------------------------------


# AC5-X1 (cross-cutting): the reserve rule and SCRUM-10's check agree for a one-row catalogue
@pytest.mark.parametrize(
    ("row", "reservations", "start", "end"),
    [
        (P10, [R(P10, 10, oct_(30), oct_(31))], WED14, WED14),
        (P10, [R(P10, 5, MON12, MON12), R(P10, 5, FRI16, FRI16)], MON12, FRI16),
        (P10, A_HOLDS_ALL, TUE13, TUE13),
        (PH10, [R(PH10, 10, SAT10, MON12)], WED14, WED14),
    ],
    ids=["outside-hold", "busiest-day", "collects-on-return", "transfer-day"],
)
def test_reserve_rule_matches_availability_check(
    row: EquipmentRow, reservations: list[Reservation], start: date, end: date
) -> None:
    checked = check_availability(
        rows=[row],
        reservations=reservations,
        start_date=start,
        end_date=end,
        event_venue=BIG,
        venues=VENUES,
        items=[RequestedItem(type=row.type, quantity=1)],
    )

    assert free(row, reservations, start, end) == checked[row.type]["available"]
