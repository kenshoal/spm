from datetime import date

import pytest

from app.block_models import VenueBlockCreate
from app.models import Slot
from app.slots import conflicts, overlaps

AM, PM, NIGHT = Slot.AM, Slot.PM, Slot.NIGHT


def day(number: int) -> date:
    return date(2026, 9, number)


# AC2-P2 (partition): overlap gives the same answer whichever period comes first
@pytest.mark.parametrize(
    "a, b, expected",
    [
        ((20, 20, [AM]), (20, 20, [PM]), []),
        ((20, 20, [AM]), (20, 20, [AM, PM]), [(day(20), AM)]),
        ((20, 20, [AM, PM, NIGHT]), (20, 20, [NIGHT]), [(day(20), NIGHT)]),
        ((20, 22, [PM]), (22, 24, [PM]), [(day(22), PM)]),
        ((20, 22, [PM]), (23, 24, [PM]), []),
        ((20, 25, [PM]), (22, 23, [PM]), [(day(22), PM), (day(23), PM)]),
        ((20, 20, [NIGHT]), (21, 21, [AM]), []),
        ((20, 20, []), (20, 20, [AM]), []),
        ((20, 20, [AM, AM]), (20, 20, [AM, AM]), [(day(20), AM)]),
        (
            (20, 21, [NIGHT, PM, AM]),
            (20, 21, [PM, NIGHT, AM]),
            [
                (day(20), AM),
                (day(20), PM),
                (day(20), NIGHT),
                (day(21), AM),
                (day(21), PM),
                (day(21), NIGHT),
            ],
        ),
    ],
    ids=[
        "disjoint-slots",
        "partial-slot",
        "full-day-vs-night",
        "inclusive-boundary",
        "adjacent-dates",
        "contained-period",
        "night-does-not-occupy-next-am",
        "empty-slots",
        "unique-pairs",
        "chronological-order",
    ],
)
def test_period_comparisons_in_both_directions(
    a: tuple, b: tuple, expected: list
) -> None:
    # Covers block-inside-booking and booking-inside-block with the same rule.
    for first, second in ((a, b), (b, a)):
        args = (
            day(first[0]),
            day(first[1]),
            first[2],
            day(second[0]),
            day(second[1]),
            second[2],
        )
        assert overlaps(*args) is bool(expected)
        assert conflicts(*args) == expected


# AC2-N1 (negative): a period ending before it starts is rejected by both checks
@pytest.mark.parametrize("function", [overlaps, conflicts], ids=["AC2-N1a", "AC2-N1b"])
@pytest.mark.parametrize("first_invalid", [True, False], ids=["case1", "case2"])
def test_reversed_ranges_are_rejected(function, first_invalid: bool) -> None:
    valid = (day(20), day(22), [AM])
    invalid = (day(22), day(20), [AM])
    args = (*invalid, *valid) if first_invalid else (*valid, *invalid)
    with pytest.raises(ValueError, match="end date"):
        function(*args)


# AC2-H2 (happy): a block identifies exactly the dates and slots it shares with a booking
def test_new_block_identifies_affected_slots_of_existing_booking() -> None:
    block = VenueBlockCreate(
        start_date="2026-09-20",
        end_date="2026-09-22",
        slots=["PM"],
        reason_category="maintenance",
    )
    # A reserved AM+PM period already exists. No event service is needed to
    # calculate its intersection; applying the block and notifying are later work.
    booking = (day(21), day(21), [AM, PM])
    blocked = (block.start_date, block.end_date, block.slots)
    assert overlaps(*booking, *blocked)
    assert conflicts(*booking, *blocked) == [(day(21), PM)]


# AC2-B1 (boundary): overlap spans a leap day and a month end
def test_leap_day_and_month_boundary() -> None:
    args = (
        date(2028, 2, 28),
        date(2028, 3, 1),
        [PM],
        date(2028, 2, 29),
        date(2028, 3, 2),
        [PM],
    )
    assert overlaps(*args)
    assert conflicts(*args) == [(date(2028, 2, 29), PM), (date(2028, 3, 1), PM)]


# AC2-B2 (boundary): overlap handles the widest possible date range
def test_boolean_check_handles_full_date_domain_without_expanding_it() -> None:
    assert overlaps(date.min, date.max, [AM], date.min, date.max, [AM])


# AC2-B3 (boundary): conflicts include the last representable date
def test_conflicts_can_include_last_representable_date() -> None:
    assert conflicts(date.max, date.max, [NIGHT], date.max, date.max, [NIGHT]) == [
        (date.max, NIGHT)
    ]
