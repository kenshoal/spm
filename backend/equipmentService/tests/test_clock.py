from datetime import UTC, date, datetime

from app.clock import singapore_today


# AC3-X1 (cross-cutting): "today" is Singapore time, not server (UTC) time
def test_today_is_singapore_date() -> None:
    # 00:30 on Mon 12 Oct in Singapore is still Sun 11 Oct in UTC.
    assert singapore_today(
        datetime(2026, 10, 11, 16, 30, tzinfo=UTC)
    ) == date(2026, 10, 12)
    # One minute before Singapore midnight is still Sun 11 Oct.
    assert singapore_today(
        datetime(2026, 10, 11, 15, 59, tzinfo=UTC)
    ) == date(2026, 10, 11)
