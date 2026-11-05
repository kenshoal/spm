"""SCRUM-40 sweep mechanics; SQL owns lifecycle and elapsed-time eligibility."""

import argparse
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from app.config import get_settings
from app.repositories import SupabaseEventRequestRepository

logger = logging.getLogger(__name__)


class AutoCompletionRepository(Protocol):
    def list_confirmed_for_auto_completion(
        self, *, after_id: str | None, limit: int
    ) -> list[dict[str, Any]]: ...

    def complete_overdue_event_request(
        self, event_request_id: str, as_of: datetime
    ) -> bool: ...


class AutoCompletionService:
    def __init__(
        self,
        repository: AutoCompletionRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        page_size: int = 1000,
    ) -> None:
        if page_size <= 0:
            raise ValueError("Completion page size must be positive")
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._page_size = page_size

    def run_once(self, as_of: datetime | None = None) -> dict[str, int]:
        instant = self._clock() if as_of is None else as_of
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Completion requires a timezone-aware clock")
        instant = instant.astimezone(UTC)
        report = {
            "examined": 0,
            "completed": 0,
            "unchanged": 0,
            "skipped_missing_end": 0,
            "failed": 0,
        }
        after_id = None
        while True:
            page = self._repository.list_confirmed_for_auto_completion(
                after_id=after_id, limit=self._page_size
            )
            if not page:
                break
            for event in page:
                event_id = event["id"]
                report["examined"] += 1
                if event["final_event_end_at"] is None:
                    report["skipped_missing_end"] += 1
                    logger.warning(
                        "Auto-completion skipped event %s: final end is not recorded",
                        event_id,
                    )
                    continue
                try:
                    changed = self._repository.complete_overdue_event_request(
                        event_id, instant
                    )
                    report["completed" if changed else "unchanged"] += 1
                except Exception:
                    report["failed"] += 1
                    logger.exception(
                        "Auto-completion failed for event %s; continuing sweep",
                        event_id,
                    )
            # A short response can be the server's row cap, not exhaustion.
            after_id = page[-1]["id"]
        logger.info("Auto-completion sweep: %s", report)
        return report


    def close(self) -> None:
        close = getattr(self._repository, "close", None)
        if callable(close):
            close()


def build_auto_completion_service() -> AutoCompletionService:
    """Create only this domain handler; the caller decides when it is scheduled."""
    return AutoCompletionService(
        SupabaseEventRequestRepository.from_settings(get_settings())
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one trusted auto-completion pass")
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args(argv)
    service = None
    try:
        service = build_auto_completion_service()
        # No supplied as_of: ordinary operation always uses the real aware clock.
        report = service.run_once()
        print(json.dumps(report, sort_keys=True))
        return 1 if report["failed"] else 0
    except Exception:
        logger.exception("Automatic completion pass could not finish")
        return 1
    finally:
        if service is not None:
            service.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
