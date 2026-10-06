"""Unit tests for app/availability.py (SCRUM-10).

Test-case IDs trace to docs/testcases/scrum_10_testcases.md. All dates are
October 2026; the event venue is Search Big Hall (building "Search Wing")
unless a test says otherwise.
"""

from copy import deepcopy
from datetime import date

import pytest

from app.availability import (
    EquipmentRow,
    RequestedItem,
    Reservation,
    Venue,
    check_availability,
    hold_window,
    needs_transfer,
)


def oct_(day: int) -> date:
    return date(2026, 10, day)


FRI9, SAT10, SUN11, MON12, TUE13, WED14, THU15, FRI16 = (
    oct_(day) for day in range(9, 17)
)

BIG = Venue("v-big", "Search Big Hall", "Search Wing")
SMALL = Venue("v-small", "Search Small Room", "Search Wing")
CLOSED = Venue("v-closed", "Search Closed Hall", "Search Wing")  # blocked venue
HARBOUR = Venue("v-harbour", "Harbour Room", "Harbour Block")
VENUES = [BIG, SMALL, CLOSED, HARBOUR]

STORE = "Store Room B"


def row(
    id: str = "p10",
    type: str = "Projector",
    qty: int = 10,
    home: str = STORE,
    status: str = "AVAILABLE",
) -> EquipmentRow:
    return EquipmentRow(
        id=id,
        type=type,
        total_owned_quantity=qty,
        home_location=home,
        operational_status=status,
    )


P10 = row()
S4 = row(id="s4", type="Speaker", qty=4)


def res(equipment_id: str, qty: int, collect: date, ret: date) -> Reservation:
    return Reservation(
        equipment_id=equipment_id,
        quantity=qty,
        collection_date=collect,
        return_date=ret,
    )


def check(
    rows: list[EquipmentRow],
    items: list[tuple[str, int]],
    start: date,
    end: date | None = None,
    reservations: list[Reservation] | None = None,
    venues: list[Venue] | None = None,
    **kwargs,
) -> dict[str, dict[str, int]]:
    return check_availability(
        rows=rows,
        reservations=reservations or [],
        start_date=start,
        end_date=end or start,
        event_venue=BIG,
        venues=VENUES if venues is None else venues,
        items=[RequestedItem(type=t, quantity=q) for t, q in items],
        **kwargs,
    )


def result(requested: int, available: int, shortfall: int) -> dict[str, int]:
    return {"requested": requested, "available": available, "shortfall": shortfall}


# --- AC1: available quantity per requested type -----------------------------


# AC1-H1, AC6 (happy): each requested type gets its own requested/available/shortfall
def test_each_requested_type_gets_its_own_result() -> None:
    rows = [P10, S4]
    reservations: list[Reservation] = []
    rows_before, reservations_before = deepcopy(rows), deepcopy(reservations)

    assert check(
        rows, [("Projector", 5), ("Speaker", 2)], WED14, reservations=reservations
    ) == {"Projector": result(5, 10, 0), "Speaker": result(2, 4, 0)}
    assert rows == rows_before
    assert reservations == reservations_before


# AC1-P1 (partition): a type split across rows is summed (6 + 4 exposes first-row-only and last-row-wins bugs)
def test_type_split_across_rows_is_summed() -> None:
    rows = [row(id="p6", qty=6), row(id="p4", qty=4, home="Store Room C")]

    assert check(rows, [("Projector", 5)], WED14)["Projector"] == result(5, 10, 0)


# AC1-P2 (partition): the requested type matches ignoring case and spaces, keyed as requested
def test_requested_type_matches_ignoring_case_and_spaces() -> None:
    assert check([P10], [("  projector ", 5)], WED14) == {
        "  projector ": result(5, 10, 0)
    }


# AC1-P3 (partition): catalogue rows differing only in case and spaces count together
def test_catalogue_types_differing_in_case_count_together() -> None:
    rows = [row(id="a", qty=6), row(id="b", type="projector ", qty=4)]

    assert check(rows, [("Projector", 5)], WED14)["Projector"] == result(5, 10, 0)


# AC1-P6 (partition): norm() never deletes spaces, so "projectorstand" is an unknown type
def test_type_without_its_space_is_unknown() -> None:
    rows = [row(id="stand", type="Projector Stand", qty=10)]

    assert check(rows, [("projectorstand", 3)], WED14) == {
        "projectorstand": result(3, 0, 3)
    }


# --- AC2: damaged, under-repair, under-maintenance and retired stock excluded ---


# AC2-H1 (happy): partly damaged stock counts only the working row
def test_partly_damaged_stock_counts_only_the_working_row() -> None:
    rows = [row(id="ok", qty=8), row(id="bad", qty=2, status="DAMAGED")]

    assert check(rows, [("Projector", 10)], WED14)["Projector"] == result(10, 8, 2)


# AC2-P1, AC2-P2, AC2-P3, AC2-P4 (partition): each non-AVAILABLE status counts 0
@pytest.mark.parametrize(
    "status",
    ["DAMAGED", "UNDER_REPAIR", "UNDER_MAINTENANCE", "RETIRED"],
    ids=["AC2-P1", "AC2-P2", "AC2-P3", "AC2-P4"],
)
def test_non_available_status_counts_zero(status: str) -> None:
    rows = [row(qty=5, status=status)]

    assert check(rows, [("Projector", 1)], WED14)["Projector"] == result(1, 0, 1)


# AC2-P5, AC3 (partition): a reservation on an excluded row is not subtracted again
def test_reservation_on_excluded_row_is_not_subtracted_again() -> None:
    rows = [row(id="ok", qty=8), row(id="bad", qty=2, status="DAMAGED")]
    reservations = [res("bad", 2, TUE13, WED14)]

    assert check(rows, [("Projector", 8)], WED14, reservations=reservations)[
        "Projector"
    ] == result(8, 8, 0)


# --- AC3: units committed to overlapping events excluded ---------------------


# AC3-H1 (happy): units reserved for an overlapping event are subtracted
def test_overlapping_reservation_is_subtracted() -> None:
    reservations = [res("p10", 4, SUN11, MON12)]

    assert check([P10], [("Projector", 5)], MON12, reservations=reservations)[
        "Projector"
    ] == result(5, 6, 0)


# AC3-P1 (partition): a reservation outside the hold is ignored
def test_reservation_outside_hold_is_ignored() -> None:
    reservations = [res("p10", 10, oct_(30), oct_(31))]

    assert check([P10], [("Projector", 5)], WED14, reservations=reservations)[
        "Projector"
    ] == result(5, 10, 0)


# AC3-P2 (partition): a reservation on another type is ignored
def test_reservation_on_another_type_is_ignored() -> None:
    reservations = [res("s4", 4, TUE13, WED14)]

    assert check([P10, S4], [("Projector", 5)], WED14, reservations=reservations)[
        "Projector"
    ] == result(5, 10, 0)


# AC3-P3 (partition): reservations that overlap each other add up
def test_reservations_overlapping_each_other_add_up() -> None:
    reservations = [res("p10", 3, SUN11, MON12), res("p10", 4, SUN11, MON12)]

    assert check([P10], [("Projector", 1)], MON12, reservations=reservations)[
        "Projector"
    ]["available"] == 3


# AC3-P4 (partition): busiest day, not the sum, of reservations that never overlap
def test_busiest_day_not_the_sum() -> None:
    reservations = [res("p10", 5, MON12, MON12), res("p10", 5, FRI16, FRI16)]

    assert check(
        [P10], [("Projector", 1)], MON12, FRI16, reservations=reservations
    )["Projector"]["available"] == 5


# AC3-P5 (partition): the busiest day is taken per row, not per type
def test_busiest_day_is_per_row_not_per_type() -> None:
    rows = [row(id="x", qty=5), row(id="y", qty=5)]
    reservations = [res("x", 5, MON12, MON12), res("y", 5, FRI16, FRI16)]

    assert check(
        rows, [("Projector", 1)], MON12, FRI16, reservations=reservations
    )["Projector"]["available"] == 0


# AC3-B1 (boundary): an over-reserved row floors at 0 and does not eat into other rows
def test_over_reserved_row_floors_at_zero() -> None:
    rows = [row(id="x", qty=5), row(id="y", qty=4)]
    reservations = [res("x", 4, TUE13, WED14), res("x", 3, TUE13, WED14)]

    assert check(rows, [("Projector", 1)], WED14, reservations=reservations)[
        "Projector"
    ]["available"] == 4


# --- AC4: unavailable from D-1 until Return Day + 1 --------------------------

# Event A on Mon 12 holds every projector from its D-1 collection day.
EVENT_A = [res("p10", 10, SUN11, MON12)]
EVENT_A_MULTI_DAY = [res("p10", 10, SUN11, WED14)]  # A runs Mon 12 to Wed 14


# AC4-H1 (happy): the hold runs from D-1 to the end date, inclusive
def test_hold_window_runs_from_d_minus_1_to_end_date() -> None:
    assert hold_window(WED14, FRI16, needs_transfer=False) == (TUE13, FRI16)


# AC4-B1, AC4-B2, AC4-B3, AC4-B4 (boundary): either side of A's hold
@pytest.mark.parametrize(
    ("event_b", "available"),
    [(TUE13, 0), (WED14, 10), (SUN11, 0), (SAT10, 10)],
    ids=["AC4-B1", "AC4-B2", "AC4-B3", "AC4-B4"],
)
def test_d_minus_1_and_return_day_plus_1(event_b: date, available: int) -> None:
    # AC4-B1: B on Tue 13 collects on A's return day (comparing against B's
    # start_date instead of its hold start would wrongly give 10).
    # AC4-B2: Return Day + 1 is the earliest free collection day.
    assert check([P10], [("Projector", 1)], event_b, reservations=EVENT_A)[
        "Projector"
    ]["available"] == available


# AC4-B5, AC4-B6 (boundary): a multi-day event is held through its last day
@pytest.mark.parametrize(
    ("event_b", "available"),
    [(THU15, 0), (FRI16, 10)],
    ids=["AC4-B5", "AC4-B6"],
)
def test_multi_day_event_held_through_last_day(event_b: date, available: int) -> None:
    assert check(
        [P10], [("Projector", 1)], event_b, reservations=EVENT_A_MULTI_DAY
    )["Projector"]["available"] == available


# --- AC5: transfer time for equipment in another building --------------------

HARBOUR_ROW = row(home="Harbour Room")
# Event A on Mon 12 using the Harbour Room row: saved collection Sat 10
# (D-1 minus one transfer day), return Mon 12.
EVENT_A_TRANSFER = [res("p10", 10, SAT10, MON12)]


# AC5-H1 (happy): equipment in another building is still counted when nothing clashes
def test_equipment_in_another_building_is_counted() -> None:
    assert check([HARBOUR_ROW], [("Projector", 5)], WED14)["Projector"] == result(
        5, 10, 0
    )


# AC5-B1, AC5-B2, AC4 (boundary): the transfer day moves the earliest free day
@pytest.mark.parametrize(
    ("event_b", "available"),
    [(WED14, 0), (THU15, 10)],
    ids=["AC5-B1", "AC5-B2"],
)
def test_transfer_day_moves_earliest_free_day(event_b: date, available: int) -> None:
    assert check(
        [HARBOUR_ROW], [("Projector", 1)], event_b, reservations=EVENT_A_TRANSFER
    )["Projector"]["available"] == available


# AC5-P1, AC4 (partition): store stock gets D-1 only in the same scenario
def test_store_stock_gets_no_transfer_day() -> None:
    assert check([P10], [("Projector", 1)], WED14, reservations=EVENT_A)[
        "Projector"
    ]["available"] == 10


# AC5-P2 to AC5-P8 (partition): which building a row is in decides the transfer day
@pytest.mark.parametrize(
    ("home_location", "transfer", "hold_start"),
    [
        ("search wing ", False, TUE13),  # event's building, odd spacing and case
        ("Search Big Hall", False, TUE13),  # the event venue's own name
        ("Search Small Room", False, TUE13),  # another venue, same building
        ("Search Closed Hall", False, TUE13),  # blocked venue still identifies it
        ("Harbour Block", True, MON12),  # another building, by location
        ("harbour room", True, MON12),  # another building, by venue name
        ("Store Room B", False, TUE13),  # matches no venue: store stock
    ],
    ids=["AC5-P2", "AC5-P3", "AC5-P4", "AC5-P5", "AC5-P6", "AC5-P7", "AC5-P8"],
)
def test_building_decides_transfer_day(
    home_location: str, transfer: bool, hold_start: date
) -> None:
    assert needs_transfer(home_location, BIG, VENUES) is transfer
    assert hold_window(WED14, WED14, needs_transfer=transfer)[0] == hold_start


# AC5-P9 (partition): a venue name shared across two buildings gets the transfer day
def test_ambiguous_venue_name_gets_transfer_day() -> None:
    venues = [
        *VENUES,
        Venue("v-studio-1", "Studio", "Search Wing"),
        Venue("v-studio-2", "Studio", "Harbour Block"),
    ]

    assert needs_transfer("Studio", BIG, venues) is True


# AC5-P10 (partition): venue names are matched before locations
def test_venue_names_are_matched_before_locations() -> None:
    venues = [*VENUES, Venue("v-annex", "Harbour Block", "Search Wing")]

    assert needs_transfer("Harbour Block", BIG, venues) is False


# AC5-X1 (cross-cutting): the transfer buffer is a parameter, not a hard-coded 1
def test_transfer_days_is_configurable() -> None:
    assert hold_window(WED14, WED14, needs_transfer=True, transfer_days=2) == (
        SUN11,
        WED14,
    )


# --- AC6: shortfall when A < Q -----------------------------------------------


# AC6-B1, AC6-B2, AC6-B3 (boundary): one more, exactly, and one fewer than available
@pytest.mark.parametrize(
    ("requested", "shortfall"),
    [(11, 1), (10, 0), (9, 0)],
    ids=["AC6-B1", "AC6-B2", "AC6-B3"],
)
def test_shortfall_boundary(requested: int, shortfall: int) -> None:
    assert check([P10], [("Projector", requested)], WED14)["Projector"] == result(
        requested, 10, shortfall
    )


# AC6-P1 (partition): each type is judged on its own
def test_each_type_judged_on_its_own() -> None:
    assert check([P10, S4], [("Projector", 12), ("Speaker", 2)], WED14) == {
        "Projector": result(12, 10, 2),
        "Speaker": result(2, 4, 0),
    }


# AC6-P2 (partition): nothing free, so the shortfall is the whole request
def test_nothing_free_shortfall_is_whole_request() -> None:
    reservations = [res("p10", 10, TUE13, WED14)]

    assert check([P10], [("Projector", 5)], WED14, reservations=reservations)[
        "Projector"
    ] == result(5, 0, 5)
