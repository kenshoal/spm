"""Singapore-time "today" (SCRUM-10, Discussion #36)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

SINGAPORE = ZoneInfo("Asia/Singapore")


def singapore_today(now: datetime) -> date:
    """The calendar date in Asia/Singapore at the aware instant `now`."""
    return now.astimezone(SINGAPORE).date()


def get_today() -> date:
    """FastAPI dependency; tests override it to freeze the clock."""
    return singapore_today(datetime.now(UTC))
