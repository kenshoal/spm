"""SCRUM-32 AC6: "today" for a booking request's start date is today in Singapore."""

from datetime import UTC, date, datetime

import pytest

from app.dependencies import singapore_today


# AC6-B3, AC6-B4, AC6-B5 (boundary): Singapore is UTC+8, so the date changes at 16:00 UTC
@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        (datetime(2026, 11, 3, 15, 59, 59, tzinfo=UTC), date(2026, 11, 3)),
        (datetime(2026, 11, 3, 16, 0, 0, tzinfo=UTC), date(2026, 11, 4)),
        (datetime(2026, 11, 3, 16, 0, 1, tzinfo=UTC), date(2026, 11, 4)),
    ],
    ids=["AC6-B3", "AC6-B4", "AC6-B5"],
)
def test_singapore_midnight_is_16_00_utc(instant: datetime, expected: date) -> None:
    assert singapore_today(instant) == expected


# AC6-X1 (cross-cutting): the UTC date is not used, a late-evening Singapore time is the next UTC day's morning
def test_the_utc_date_is_not_the_singapore_date() -> None:
    assert singapore_today(datetime(2026, 12, 31, 20, 0, tzinfo=UTC)) == date(2027, 1, 1)
