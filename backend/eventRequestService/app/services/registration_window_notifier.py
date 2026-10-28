"""SCRUM-38 AC3: tell the Organiser and Coordinator when registration opens or closes.

One pass looks at Confirmed events whose opening or closing time fell inside the
lookback and sends one notice per boundary and person. It keeps no record of its
own: every send carries a key built from the event, the boundary time and the
person, and notificationService stores a repeated key once. So a restart, an
overlapping pass or a missed run is harmless: the next pass repeats what it has
to and the duplicates are dropped. A boundary older than the lookback is not
announced late (nobody needs "registration opened last month"), and an
Organiser who moves the window gets a fresh notice for the new time.

The shared runner (SCRUM-40) only supplies the timer; the rules are here.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.config import (
    get_notification_settings,
    get_periodic_task_settings,
    get_settings,
)
from app.repositories.registration_repository import SupabaseRegistrationRepository
from app.services.notification_client import NotificationClient

logger = logging.getLogger(__name__)


class RegistrationWindowRepository(Protocol):
    def list_window_boundaries(
        self, *, since: datetime, until: datetime, after_id: str | None, limit: int
    ) -> list[dict[str, Any]]: ...

    def latest_coordinator_id(self, event_id: str) -> str | None: ...


class RegistrationWindowNotifier:
    def __init__(
        self,
        repository: RegistrationWindowRepository,
        notification_client: Any,
        *,
        lookback: timedelta,
        clock: Callable[[], datetime] | None = None,
        page_size: int = 1000,
    ) -> None:
        if lookback <= timedelta(0):
            raise ValueError("Registration notice lookback must be positive")
        if page_size <= 0:
            raise ValueError("Registration notice page size must be positive")
        self._repository = repository
        self._notifications = notification_client
        self._lookback = lookback
        self._clock = clock or (lambda: datetime.now(UTC))
        self._page_size = page_size

    def run_once(self, as_of: datetime | None = None) -> dict[str, int]:
        instant = self._clock() if as_of is None else as_of
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Registration notices require a timezone-aware clock")
        until = instant.astimezone(UTC)
        since = until - self._lookback
        report = {"examined": 0, "notified": 0, "failed": 0}
        after_id: str | None = None
        while True:
            page = self._repository.list_window_boundaries(
                since=since, until=until, after_id=after_id, limit=self._page_size
            )
            if not page:
                break
            for event in page:
                report["examined"] += 1
                self._notify_event(event, since, until, report)
            # A short page can be the server's row cap, not the end: read on until empty.
            after_id = page[-1]["id"]
        return report

    def _notify_event(
        self,
        event: dict[str, Any],
        since: datetime,
        until: datetime,
        report: dict[str, int],
    ) -> None:
        boundaries = [
            (kind, moment)
            for kind, moment in (
                ("opened", _as_datetime(event.get("registration_opens_at"))),
                ("closed", _as_datetime(event.get("registration_closes_at"))),
            )
            if moment is not None and since <= moment <= until
        ]
        if not boundaries:
            return
        recipients = [event["organiser_id"]]
        try:
            coordinator_id = self._repository.latest_coordinator_id(event["id"])
        except Exception:
            report["failed"] += 1
            logger.exception(
                "Could not find the coordinator of event request %s for a "
                "registration notice; telling the organiser only",
                event["id"],
            )
            coordinator_id = None
        if coordinator_id is not None and coordinator_id not in recipients:
            recipients.append(coordinator_id)
        for kind, moment in boundaries:
            for recipient_id in recipients:
                try:
                    self._notifications.notify_registration_window(
                        kind=kind,
                        event_request_id=event["id"],
                        event_name=event.get("event_name"),
                        boundary_at=moment,
                        recipient_id=recipient_id,
                    )
                    report["notified"] += 1
                except Exception:
                    report["failed"] += 1
                    logger.exception(
                        "Registration %s notice for event request %s failed; "
                        "continuing the pass",
                        kind,
                        event["id"],
                    )


def build_registration_window_notifier() -> RegistrationWindowNotifier:
    """Create only this handler; the caller decides when it is scheduled."""
    settings = get_settings()
    return RegistrationWindowNotifier(
        SupabaseRegistrationRepository.from_settings(settings),
        NotificationClient.from_settings(get_notification_settings()),
        lookback=timedelta(hours=get_periodic_task_settings().registration_window_lookback_hours),
    )


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if moment.tzinfo is None:
        return None
    return moment.astimezone(UTC)
