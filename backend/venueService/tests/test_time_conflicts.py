"""SCRUM-20: venue booking conflict rules on 15-minute time ranges.

Case IDs match docs/testcases/scrum_20_testcases.md. These are the pure rules on
SCRUM-65's booking model (0050): an inclusive date range with one start and end
minute on each date. Applying them inside the database is a later increment.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.booking_models import BookingRequestStatus
from app.models import Venue
from app.time_conflicts import (
    BookingTimeError,
    TimedBooking,
    affected_by_timing_change,
    check_booking_time,
    find_conflicts,
    padded_range,
)

DAY = date(2026, 10, 20)
VENUE = "venue-1"


def m(clock: str) -> int:
    """Minutes after midnight for "HH:MM", including "24:00"."""
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


def venue(setup: int = 0, turnaround: int = 0) -> Venue:
    return Venue(
        id=VENUE,
        name="Hall",
        location="Campus",
        max_capacity=50,
        setup_minutes=setup,
        turnaround_minutes=turnaround,
    )


def booking(
    booking_id: str,
    start: str,
    end: str,
    *,
    dates: tuple[date, date] = (DAY, DAY),
    venue_id: str = VENUE,
    status: BookingRequestStatus = BookingRequestStatus.APPROVED,
) -> TimedBooking:
    return TimedBooking(
        id=booking_id,
        venue_id=venue_id,
        start_date=dates[0],
        end_date=dates[1],
        start_minute=m(start),
        end_minute=m(end),
        status=status,
    )


def conflict_ids(
    hall: Venue,
    start: str,
    end: str,
    bookings: list[TimedBooking],
    *,
    dates: tuple[date, date] = (DAY, DAY),
    **kwargs,
) -> list[str]:
    found = find_conflicts(hall, *dates, m(start), m(end), bookings, **kwargs)
    return [b.id for b in found]


def refusal(start: str, end: str, setup: int = 0, turnaround: int = 0) -> str:
    with pytest.raises(BookingTimeError) as error:
        check_booking_time(m(start), m(end), setup, turnaround)
    return error.value.code


# AC2-H1 (happy): a booking on 15-minute steps inside the window is valid
def test_booking_on_steps_inside_the_window_is_valid() -> None:
    check_booking_time(m("10:00"), m("12:00"))


# AC2-B1 (boundary): the window runs from 07:00 to 24:00
@pytest.mark.parametrize(("start", "end"), [("07:00", "08:00"), ("23:45", "24:00")])
def test_times_at_the_window_limits_are_valid(start: str, end: str) -> None:
    check_booking_time(m(start), m(end))


# AC2-B1 (boundary): one step outside the window is refused
@pytest.mark.parametrize(("start", "end"), [("06:45", "08:00"), ("23:00", "24:15")])
def test_times_one_step_outside_the_window_are_refused(start: str, end: str) -> None:
    assert refusal(start, end) == "outside_operating_window"


# AC2-B2 (boundary): the shortest booking is one 15-minute step
def test_shortest_booking_is_one_step() -> None:
    check_booking_time(m("10:00"), m("10:15"))


# AC2-B2 (boundary): an end at or before the start is refused
@pytest.mark.parametrize(("start", "end"), [("10:00", "10:00"), ("10:15", "10:00")])
def test_end_not_after_start_is_refused(start: str, end: str) -> None:
    assert refusal(start, end) == "end_not_after_start"


# AC2-N1 (negative): times off the 15-minute step are refused
@pytest.mark.parametrize(("start", "end"), [("10:10", "12:00"), ("10:00", "11:05")])
def test_off_step_times_are_refused(start: str, end: str) -> None:
    assert refusal(start, end) == "off_step"


# AC3-H1 (happy): the Week 7 example: 10:00-12:00 with 30 / 45 occupies 09:30-12:45
def test_week_7_example_padding() -> None:
    assert padded_range(m("10:00"), m("12:00"), 30, 45) == (m("09:30"), m("12:45"))


# AC3-P1 (partition): no setup or turnaround leaves the time as booked
def test_no_padding_leaves_the_booked_time() -> None:
    assert padded_range(m("10:00"), m("12:00"), 0, 0) == (m("10:00"), m("12:00"))


# AC3-B1 (boundary): setup must stay inside the window
def test_setup_must_stay_inside_the_window() -> None:
    check_booking_time(m("07:30"), m("09:00"), 30, 0)
    assert refusal("07:15", "09:00", 30, 0) == "setup_outside_window"


# AC3-B2 (boundary): turnaround must stay inside the window
def test_turnaround_must_stay_inside_the_window() -> None:
    check_booking_time(m("22:00"), m("23:15"), 0, 45)
    assert refusal("22:00", "23:30", 0, 45) == "turnaround_outside_window"


# AC3-H2 (happy): padding creates a conflict the booked times alone would not
def test_padding_creates_a_conflict() -> None:
    existing = [booking("A", "10:00", "12:00")]

    assert conflict_ids(venue(30, 45), "12:15", "13:00", existing) == ["A"]
    assert conflict_ids(venue(0, 0), "12:15", "13:00", existing) == []


# AC1-H1 (happy): an overlapping approved booking is a conflict
def test_overlapping_approved_booking_is_a_conflict() -> None:
    assert conflict_ids(venue(), "11:00", "13:00", [booking("A", "10:00", "12:00")]) == ["A"]


# AC1-H2 (happy): a free time has no conflict
def test_free_time_has_no_conflict() -> None:
    assert conflict_ids(venue(), "13:00", "14:00", [booking("A", "10:00", "12:00")]) == []


# AC1-H3 (happy): every clashing booking is reported, in start order
def test_every_conflict_is_reported_in_start_order() -> None:
    existing = [
        booking("B", "11:00", "12:00"),
        booking("C", "14:00", "15:00"),
        booking("A", "09:00", "10:00"),
    ]

    assert conflict_ids(venue(), "09:30", "11:30", existing) == ["A", "B"]


# AC1-P1 (partition): pending, rejected and cancelled requests never conflict
@pytest.mark.parametrize(
    "status",
    [
        BookingRequestStatus.PENDING,
        BookingRequestStatus.REJECTED,
        BookingRequestStatus.CANCELLED,
    ],
)
def test_only_approved_bookings_count(status: BookingRequestStatus) -> None:
    existing = [booking("A", "10:00", "12:00", status=status)]

    assert conflict_ids(venue(), "10:00", "12:00", existing) == []


# AC1-P2 (partition): other venues and other dates never conflict
def test_other_venues_and_dates_never_conflict() -> None:
    existing = [
        booking("other-venue", "10:00", "12:00", venue_id="venue-2"),
        booking("next-day", "10:00", "12:00", dates=(date(2026, 10, 21),) * 2),
    ]

    assert conflict_ids(venue(), "10:00", "12:00", existing) == []


# AC1-P3 (partition): multi-day bookings clash when their date ranges share a day
def test_multi_day_bookings_clash_on_a_shared_day() -> None:
    existing = [booking("A", "10:00", "12:00", dates=(date(2026, 10, 19), DAY))]

    assert conflict_ids(
        venue(), "11:00", "13:00", existing, dates=(DAY, date(2026, 10, 22))
    ) == ["A"]


# AC1-P4 (partition): same times on date ranges that share no day never clash
def test_same_times_on_separate_date_ranges_do_not_clash() -> None:
    existing = [booking("A", "10:00", "12:00", dates=(date(2026, 10, 19), DAY))]

    assert conflict_ids(
        venue(),
        "10:00",
        "12:00",
        existing,
        dates=(date(2026, 10, 21), date(2026, 10, 22)),
    ) == []


# AC1-B2 (boundary): date ranges are inclusive at both ends
def test_date_ranges_are_inclusive() -> None:
    existing = [booking("A", "10:00", "12:00", dates=(DAY, date(2026, 10, 21)))]
    hall = venue()

    assert conflict_ids(
        hall, "10:00", "12:00", existing, dates=(date(2026, 10, 21),) * 2
    ) == ["A"]
    assert conflict_ids(
        hall, "10:00", "12:00", existing, dates=(date(2026, 10, 22),) * 2
    ) == []


# AC1-B1 (boundary): touching bookings do not overlap; one step of overlap does
def test_touching_bookings_do_not_overlap() -> None:
    existing = [booking("A", "10:00", "12:00")]

    assert conflict_ids(venue(), "12:00", "13:00", existing) == []
    assert conflict_ids(venue(), "11:45", "13:00", existing) == ["A"]


# AC5-B1 (boundary): a gap equal to turnaround plus setup is allowed; one step less is not
def test_gap_after_a_booking_must_cover_turnaround_and_setup() -> None:
    existing = [booking("A", "10:00", "12:00")]

    assert conflict_ids(venue(30, 45), "13:15", "14:00", existing) == []
    assert conflict_ids(venue(30, 45), "13:00", "14:00", existing) == ["A"]


# AC5-B2 (boundary): the same boundary applies before an existing booking
def test_gap_before_a_booking_must_cover_turnaround_and_setup() -> None:
    existing = [booking("A", "14:00", "15:00")]

    assert conflict_ids(venue(30, 45), "11:00", "12:45", existing) == []
    assert conflict_ids(venue(30, 45), "11:00", "13:00", existing) == ["A"]


# AC5-P1 (partition): turnaround only, and setup only
@pytest.mark.parametrize(
    ("setup", "turnaround", "allowed", "refused"),
    [(0, 45, "12:45", "12:30"), (30, 0, "12:30", "12:15")],
)
def test_turnaround_only_and_setup_only(
    setup: int, turnaround: int, allowed: str, refused: str
) -> None:
    existing = [booking("A", "10:00", "12:00")]
    hall = venue(setup, turnaround)

    assert conflict_ids(hall, allowed, "14:00", existing) == []
    assert conflict_ids(hall, refused, "14:00", existing) == ["A"]


# AC4-H1 (happy): moving a booking onto a booked time reports the conflict
def test_moving_onto_a_booked_time_conflicts() -> None:
    existing = [booking("A", "10:00", "12:00"), booking("B", "14:00", "15:00")]

    assert conflict_ids(venue(), "11:00", "12:00", existing, exclude_id="B") == ["A"]


# AC4-P1 (partition): a booking never conflicts with itself
def test_a_booking_never_conflicts_with_itself() -> None:
    existing = [booking("B", "14:00", "15:00")]

    assert conflict_ids(venue(), "14:00", "16:00", existing, exclude_id="B") == []


# AC4-H2 (happy): moving to a free time is allowed
def test_moving_to_a_free_time_is_allowed() -> None:
    existing = [booking("A", "10:00", "12:00"), booking("B", "14:00", "15:00")]

    assert conflict_ids(venue(), "16:00", "17:00", existing, exclude_id="B") == []


def affected_ids(
    bookings: list[TimedBooking], old: tuple[int, int], new: tuple[int, int]
) -> list[str]:
    return [b.id for b in affected_by_timing_change(VENUE, bookings, old, new, DAY)]


# AC6-H1 (happy): raising turnaround finds both bookings of a newly conflicting pair
def test_raising_turnaround_finds_newly_conflicting_bookings() -> None:
    existing = [
        booking("A", "10:00", "12:00"),
        booking("B", "12:30", "14:00"),
        booking("C", "16:00", "17:00"),
    ]

    assert affected_ids(existing, (0, 0), (0, 45)) == ["A", "B"]


# AC6-P1 (partition): an unchanged save affects nothing
def test_unchanged_times_affect_nothing() -> None:
    existing = [booking("A", "10:00", "12:00"), booking("B", "12:00", "13:00")]

    assert affected_ids(existing, (30, 45), (30, 45)) == []


# AC6-P2 (partition): lowering the times affects nothing
def test_lowering_times_affects_nothing() -> None:
    existing = [booking("A", "10:00", "12:00"), booking("B", "13:15", "14:00")]

    assert affected_ids(existing, (30, 45), (0, 0)) == []


# AC6-P3 (partition): only newly conflicting bookings are affected
def test_only_new_conflicts_are_affected() -> None:
    existing = [
        booking("A", "10:00", "12:00"),
        booking("B", "12:15", "13:00"),
        booking("C", "13:30", "14:00"),
    ]

    assert affected_ids(existing, (0, 30), (0, 45)) == ["B", "C"]


# AC6-B1 (boundary): a booking pushed outside the window by new padding is affected
def test_padding_pushed_outside_the_window_is_affected() -> None:
    assert affected_ids([booking("A", "07:00", "08:00")], (0, 0), (30, 0)) == ["A"]


# AC6-P4 (partition): only approved bookings are considered
def test_only_approved_bookings_are_affected() -> None:
    existing = [
        booking("P", "10:00", "12:00", status=BookingRequestStatus.PENDING),
        booking("A", "12:15", "13:00"),
    ]

    assert affected_ids(existing, (0, 0), (0, 45)) == []


# AC6-B2 (boundary): bookings that ended before today are not flagged; one that
# ends today, including a multi-day one that started earlier, still is
def test_ended_bookings_are_not_affected() -> None:
    yesterday = date(2026, 10, 19)
    existing = [
        booking("A", "10:00", "12:00", dates=(yesterday, yesterday)),
        booking("B", "12:30", "14:00", dates=(yesterday, yesterday)),
        booking("C", "10:00", "12:00", dates=(yesterday, DAY)),
        booking("D", "12:30", "14:00"),
    ]

    assert affected_ids(existing, (0, 0), (0, 45)) == ["C", "D"]


# AC6-P5 (partition): a newly conflicting pair must share a day
def test_new_conflict_needs_a_shared_day() -> None:
    existing = [
        booking("A", "10:00", "12:00", dates=(DAY, DAY)),
        booking("B", "12:30", "14:00", dates=(date(2026, 10, 21),) * 2),
    ]

    assert affected_ids(existing, (0, 0), (0, 45)) == []
