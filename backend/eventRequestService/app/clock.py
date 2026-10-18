"""Injectable clock (SCRUM-21 D9)."""

from datetime import UTC, datetime


def get_now() -> datetime:
    """FastAPI dependency returning the aware UTC instant; tests override it."""
    return datetime.now(UTC)
