"""SCRUM-38 AC3: tell the Organiser and Coordinator when registration opens or closes.

Case IDs match docs/testcases/scrum_38_testcases.md. The repository is faked; it
filters by range the way the real query does.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest

from app import main as application
from app.config import PeriodicTaskSettings
from app.repositories.registration_repository import SupabaseRegistrationRepository
from app.services.notification_client import NotificationClient
from app.services.registration_window_notifier import RegistrationWindowNotifier

NOW = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)
LOOKBACK = timedelta(hours=72)


class FakeWindowRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.coordinators: dict[str, str] = {}
        self.coordinator_lookup_fails_for: set[str] = set()
        self.queries: list[tuple[datetime, datetime]] = []

    def add(self, event_id: str, opens: datetime | None, closes: datetime | None,
            status: str = "Confirmed", coordinator: str | None = "coord-1") -> None:
        self.events.append({
            "id": event_id, "status": status, "event_name": f"Event {event_id}",
            "organiser_id": f"org-{event_id}",
            "registration_opens_at": opens, "registration_closes_at": closes,
        })
        if coordinator:
            self.coordinators[event_id] = coordinator

    def list_window_boundaries(
        self, *, since: datetime, until: datetime, after_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        self.queries.append((since, until))
        def inside(value: datetime | None) -> bool:
            return value is not None and since <= value <= until
        rows = [
            e for e in sorted(self.events, key=lambda e: e["id"])
            if e["status"] == "Confirmed"
            and (inside(e["registration_opens_at"]) or inside(e["registration_closes_at"]))
            and (after_id is None or e["id"] > after_id)
        ]
        return rows[:limit]

    def latest_coordinator_id(self, event_id: str) -> str | None:
        if event_id in self.coordinator_lookup_fails_for:
            raise RuntimeError("assignments unavailable")
        return self.coordinators.get(event_id)


class SpyNotificationClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_for: set[str] = set()

    def notify_registration_window(self, **kwargs: Any) -> None:
        if kwargs["recipient_id"] in self.fail_for:
            raise RuntimeError("sender bug")
        self.sent.append(kwargs)


def make(repo: FakeWindowRepository, spy: SpyNotificationClient,
         **kwargs: Any) -> RegistrationWindowNotifier:
    return RegistrationWindowNotifier(
        repo, spy, lookback=LOOKBACK, clock=lambda: NOW, **kwargs
    )


def pairs(spy: SpyNotificationClient) -> list[tuple[str, str]]:
    return sorted((n["recipient_id"], n["kind"]) for n in spy.sent)


# AC3-H1 (happy): Registration that opened inside the lookback tells the Organiser and
# the Coordinator once, naming the boundary time.
def test_opening_notifies_the_organiser_and_the_coordinator() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    opens = NOW - timedelta(hours=1)
    repo.add("e1", opens, NOW + timedelta(days=5))

    report = make(repo, spy).run_once()

    assert pairs(spy) == [("coord-1", "opened"), ("org-e1", "opened")]
    assert all(n["boundary_at"] == opens and n["event_request_id"] == "e1"
               and n["event_name"] == "Event e1" for n in spy.sent)
    assert report["notified"] == 2


# AC3-H2 (happy): Registration that closed inside the lookback tells both of them.
def test_closing_notifies_the_organiser_and_the_coordinator() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    repo.add("e1", NOW - timedelta(days=10), NOW - timedelta(minutes=5))

    make(repo, spy).run_once()

    assert pairs(spy) == [("coord-1", "closed"), ("org-e1", "closed")]


# AC3-P1 (partition): A window that both opened and closed inside the lookback sends
# one notice of each kind per person.
def test_opening_and_closing_in_one_pass_send_both_notices() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    repo.add("e1", NOW - timedelta(hours=30), NOW - timedelta(hours=2))

    make(repo, spy).run_once()

    assert pairs(spy) == [
        ("coord-1", "closed"), ("coord-1", "opened"),
        ("org-e1", "closed"), ("org-e1", "opened"),
    ]


@pytest.mark.parametrize(
    ("opens_offset", "expected"),
    [
        (timedelta(seconds=1), 0),       # one second in the future: not yet
        (timedelta(0), 2),               # exactly now: reached
        (-LOOKBACK, 2),                  # exactly at the edge of the lookback: still caught up
        (-LOOKBACK - timedelta(seconds=1), 0),  # just older than the lookback: not sent
    ],
    ids=["AC3-B1a", "AC3-B1b", "AC3-B1c", "AC3-B1d"],
)
# AC3-B1 (boundary): A boundary is announced from the moment it is reached until the
# lookback ends: not one second early, not one second late.
def test_boundary_edges(opens_offset: timedelta, expected: int) -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    repo.add("e1", NOW + opens_offset, NOW + timedelta(days=30))

    make(repo, spy).run_once()

    assert len(spy.sent) == expected


# AC3-N1 (negative): Events that are not Confirmed, have no window, or whose window is
# outside the lookback send nothing.
def test_ineligible_events_send_nothing() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    recent = NOW - timedelta(hours=1)
    repo.add("cancelled", recent, NOW + timedelta(days=5), status="Cancelled")
    repo.add("no-window", None, None)
    repo.add("old", NOW - timedelta(days=30), NOW - timedelta(days=20))

    make(repo, spy).run_once()

    assert spy.sent == []


# AC3-X1 (cross-cutting): Passes are repeatable: running twice sends the same notices
# with the same boundary, so notificationService's key keeps one copy per person.
def test_running_twice_repeats_identical_notices() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    repo.add("e1", NOW - timedelta(hours=1), NOW + timedelta(days=5))
    notifier = make(repo, spy)

    notifier.run_once()
    first = list(spy.sent)
    spy.sent.clear()
    notifier.run_once()

    assert spy.sent == first


# AC3-N2 (negative): A Coordinator that cannot be found does not stop the Organiser's
# notice or the other events.
def test_coordinator_lookup_failure_is_contained() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    repo.add("e1", NOW - timedelta(hours=1), NOW + timedelta(days=5))
    repo.add("e2", NOW - timedelta(hours=1), NOW + timedelta(days=5))
    repo.coordinator_lookup_fails_for.add("e1")

    report = make(repo, spy).run_once()

    assert pairs(spy) == [
        ("coord-1", "opened"), ("org-e1", "opened"), ("org-e2", "opened"),
    ]
    assert report["failed"] == 1


# AC3-N3 (negative): A sender failure for one person is contained; the rest still go.
def test_sender_failure_does_not_stop_the_pass() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    repo.add("e1", NOW - timedelta(hours=1), NOW + timedelta(days=5))
    repo.add("e2", NOW - timedelta(hours=1), NOW + timedelta(days=5))
    spy.fail_for.add("org-e1")

    report = make(repo, spy).run_once()

    assert sorted(n["recipient_id"] for n in spy.sent) == ["coord-1", "coord-1", "org-e2"]
    assert report["failed"] == 1


# AC3-N4 (negative): A clock without a time zone is refused instead of guessed.
def test_naive_clock_is_refused() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()

    with pytest.raises(ValueError, match="timezone-aware"):
        make(repo, spy).run_once(datetime(2030, 1, 15, 12, 0))  # naive on purpose


# AC3-B2 (boundary): Paging covers every event, not just the first page.
def test_every_page_is_read() -> None:
    repo, spy = FakeWindowRepository(), SpyNotificationClient()
    for i in range(5):
        repo.add(f"e{i}", NOW - timedelta(hours=1), NOW + timedelta(days=5), coordinator=None)

    make(repo, spy, page_size=2).run_once()

    assert len(spy.sent) == 5


OPENED_AT = datetime(2030, 1, 15, 8, 0, tzinfo=UTC)


def capture(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    posted: list[dict] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        posted.append(kwargs["json"])  # type: ignore[arg-type]
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    return posted


# AC3-H3 (happy): The client posts an opening notice to one person with a key built from
# the event, the boundary time and that person.
def test_window_notice_posts_the_agreed_shape(monkeypatch) -> None:
    posted = capture(monkeypatch)

    NotificationClient("https://n.example.com/events").notify_registration_window(
        kind="opened", event_request_id="event-1", event_name="Dinner",
        boundary_at=OPENED_AT, recipient_id="org-1",
    )

    assert posted == [{
        "event_type": "registration_opened",
        "recipient_id": "org-1",
        "event_id": str(uuid5(
            NAMESPACE_URL, "registration-opened:event-1:2030-01-15T08:00:00+00:00:org-1"
        )),
        "payload": {
            "event_request_id": "event-1",
            "event_name": "Dinner",
            "boundary_at": "2030-01-15T08:00:00+00:00",
        },
    }]


# AC3-X2 (cross-cutting): The key depends on the boundary time, so a moved window gets
# a fresh notice, while the same boundary always gets the same key.
def test_window_notice_key_follows_the_boundary(monkeypatch) -> None:
    posted = capture(monkeypatch)
    client = NotificationClient("https://n.example.com/events")
    for moment in (OPENED_AT, OPENED_AT, OPENED_AT + timedelta(hours=2)):
        client.notify_registration_window(
            kind="opened", event_request_id="event-1", event_name="Dinner",
            boundary_at=moment, recipient_id="org-1",
        )

    keys = [n["event_id"] for n in posted]
    assert keys[0] == keys[1]
    assert keys[0] != keys[2]


# AC3-X3 (cross-cutting): The database query asks only for Confirmed events whose
# opening or closing time falls inside the range, oldest id first, a page at a time.
def test_window_query_selects_confirmed_events_with_a_boundary_in_range() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"id": "e1"}])

    repo = SupabaseRegistrationRepository(
        "https://example.supabase.co", "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    since, until = NOW - LOOKBACK, NOW

    rows = repo.list_window_boundaries(since=since, until=until, after_id="e0", limit=50)

    assert rows == [{"id": "e1"}]
    params = seen[0].url.params
    assert seen[0].url.path == "/rest/v1/event_requests"
    assert params["status"] == "eq.Confirmed"
    assert params["order"] == "id.asc"
    assert params["limit"] == "50"
    assert params["id"] == "gt.e0"
    assert params["select"] == (
        "id,event_name,organiser_id,registration_opens_at,registration_closes_at"
    )
    assert params["or"] == (
        "(and(registration_opens_at.gte.2030-01-12T12:00:00Z,"
        "registration_opens_at.lte.2030-01-15T12:00:00Z),"
        "and(registration_closes_at.gte.2030-01-12T12:00:00Z,"
        "registration_closes_at.lte.2030-01-15T12:00:00Z))"
    )


# AC3-X4 (cross-cutting): The notices are off by default, switched on separately from
# automatic completion, and use the shared runner.
def test_window_notices_are_opt_in_and_use_the_shared_runner(monkeypatch) -> None:
    for name in ("AUTO_COMPLETION_ENABLED", "REGISTRATION_WINDOW_NOTICES_ENABLED",
                 "REGISTRATION_WINDOW_LOOKBACK_HOURS"):
        monkeypatch.delenv(name, raising=False)
    defaults = PeriodicTaskSettings(_env_file=None)
    assert defaults.registration_window_notices_enabled is False
    assert defaults.registration_window_lookback_hours == 72
    monkeypatch.setattr(application, "get_periodic_task_settings", lambda: defaults)
    assert application.build_periodic_task_runner() is None

    enabled = PeriodicTaskSettings(
        _env_file=None, registration_window_notices_enabled=True
    )
    passes: list[str] = []

    class Prepared:
        def run_once(self) -> None:
            passes.append("window")

    monkeypatch.setattr(application, "get_periodic_task_settings", lambda: enabled)
    monkeypatch.setattr(
        application, "build_registration_window_notifier", lambda: Prepared()
    )
    runner = application.build_periodic_task_runner()

    assert runner is not None
    runner.run_once()
    assert passes == ["window"]


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"], ids=["zero", "negative", "nan", "inf"])
# AC3-N5 (negative): A lookback that is not a positive finite number is refused at start-up.
def test_lookback_setting_must_be_positive_and_finite(value: str) -> None:
    with pytest.raises(ValueError):
        PeriodicTaskSettings(_env_file=None, registration_window_lookback_hours=value)
