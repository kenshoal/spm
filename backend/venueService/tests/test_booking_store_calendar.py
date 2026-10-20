"""The in-memory store's approved-bookings window read (SCRUM-31)."""

from datetime import date

from booking_support import BASE_TIME, STAFF, seed_booking

from app.booking_models import BookingRequestStatus
from app.booking_repository import booking_repository


def approved(venue_id: str, start: date, end: date, **extra):
    return seed_booking(
        venue_id=venue_id,
        start_date=start,
        end_date=end,
        status=BookingRequestStatus.APPROVED,
        decided_by=STAFF,
        decided_at=BASE_TIME,
        **extra,
    )


# AC2-X3 (cross-cutting): only approved bookings of that venue that touch the window are returned
def test_memory_store_returns_only_approved_bookings_of_the_venue_in_the_window() -> None:
    inside = approved("venue-1", date(2026, 10, 30), date(2026, 11, 2))
    approved("venue-2", date(2026, 10, 10), date(2026, 10, 10))
    seed_booking(venue_id="venue-1", start_date=date(2026, 10, 10), end_date=date(2026, 10, 10))
    approved("venue-1", date(2026, 12, 1), date(2026, 12, 1))
    approved("venue-1", date(2026, 9, 1), date(2026, 9, 30))

    result = booking_repository.list_approved_for_venue("venue-1", date(2026, 10, 1), date(2026, 10, 31))

    assert [item.id for item in result] == [inside.id]


# AC2-X3 (cross-cutting): the window edges are inclusive, one day outside is not
def test_memory_store_window_edges_are_inclusive() -> None:
    on_last_day = approved("venue-1", date(2026, 10, 31), date(2026, 10, 31))
    on_first_day = approved("venue-1", date(2026, 9, 28), date(2026, 10, 1))
    approved("venue-1", date(2026, 11, 1), date(2026, 11, 2))
    approved("venue-1", date(2026, 9, 29), date(2026, 9, 30))

    result = booking_repository.list_approved_for_venue("venue-1", date(2026, 10, 1), date(2026, 10, 31))

    assert sorted(item.id for item in result) == sorted([on_last_day.id, on_first_day.id])
