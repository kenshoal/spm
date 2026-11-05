"""Release 1 hotfixes #1 and #2: the served app's real wiring, not the test fakes.

The API suites inject a fake repository and a spy client, so they cannot notice a
service the served app builds without its notifier, or a timer calling a method
only the fake has. These tests exercise the production builders and repository.
"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.controllers import registration_controller
from app.repositories import SupabaseRepositoryError
from app.repositories.waitlist_repository import SupabaseWaitlistRepository
from app.services.waitlist_notification_relay import WaitlistNotificationRelay
from app.services.waitlist_timer import WaitlistTimer

NOW = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)
NOTICE_URL = "http://notifications.test/notifications/events"


def make_repository(handler) -> SupabaseWaitlistRepository:  # type: ignore[no-untyped-def]
    return SupabaseWaitlistRepository(
        "https://example.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )


# AC1-H1 (happy): the service the served app builds on first use can send notices
def test_served_registration_service_has_a_working_notifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTIFICATION_SERVICE_URL", NOTICE_URL)
    monkeypatch.setattr(
        registration_controller,
        "get_settings",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        registration_controller.SupabaseRegistrationRepository,
        "from_settings",
        classmethod(lambda cls, settings: object()),
    )
    monkeypatch.setattr(
        registration_controller.SupabaseCoordinatorAssignmentRepository,
        "from_settings",
        classmethod(lambda cls, settings: object()),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(registration_service=None))
    )

    service = registration_controller.get_registration_service(request)

    assert service.notification_client._url == NOTICE_URL
    assert request.app.state.registration_service is service


# AC2-H1 (happy): one timer pass calls the database function with the clock
def test_timer_pass_calls_the_database_function() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    make_repository(handler).process_waitlist_timers(NOW)

    assert seen[0].url.path.endswith("/rpc/process_waitlist_timers")
    assert json.loads(seen[0].content) == {"p_now": NOW.isoformat()}


# AC2-N1 (negative): a failed pass is an error, so the runner logs and retries it
def test_timer_pass_failure_is_raised() -> None:
    repository = make_repository(lambda request: httpx.Response(500, json={"code": "XX000"}))

    with pytest.raises(SupabaseRepositoryError):
        repository.process_waitlist_timers(NOW)


# AC2-H2 (happy): only unpublished notices are read, oldest first
def test_pending_outbox_reads_unpublished_notices_oldest_first() -> None:
    seen: list[httpx.Request] = []
    row = {
        "id": "n1",
        "recipient_id": "a1",
        "event_type": "waitlist_offered",
        "idempotency_key": "k1",
        "payload": {"entry_id": "e1"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[row])

    assert make_repository(handler).pending_outbox() == [row]
    params = seen[0].url.params
    assert seen[0].url.path.endswith("/waitlist_notification_outbox")
    assert params["published_at"] == "is.null"
    assert params["order"] == "occurred_at.asc"


# AC2-H3 (happy): marking stamps only still-unpublished rows and counts them
def test_mark_published_stamps_unpublished_rows_and_counts_them() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"id": "n1"}])

    assert make_repository(handler).mark_published(["n1"], NOW) == 1
    assert seen[0].method == "PATCH"
    assert seen[0].url.params["id"] == "in.(n1)"
    assert seen[0].url.params["published_at"] == "is.null"
    assert json.loads(seen[0].content) == {"published_at": NOW.isoformat()}


# AC2-B1 (boundary): marking nothing makes no call
def test_mark_published_with_no_ids_makes_no_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert make_repository(handler).mark_published([], NOW) == 0


# AC2-X1 (cross-cutting): the real repository satisfies the served timer end to end
def test_timer_runs_on_the_real_repository() -> None:
    published: list[str] = []
    row = {
        "id": "n1",
        "recipient_id": "a1",
        "event_type": "waitlist_offered",
        "idempotency_key": "k1",
        "payload": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rpc/process_waitlist_timers"):
            return httpx.Response(204)
        if request.method == "GET":
            return httpx.Response(200, json=[row])
        published.append(request.url.params["id"])
        return httpx.Response(200, json=[{"id": "n1"}])

    client = SimpleNamespace(notify_waitlist_notice=lambda **kwargs: True)
    repository = make_repository(handler)
    timer = WaitlistTimer(
        repository, WaitlistNotificationRelay(repository, client), clock=lambda: NOW
    )

    result = timer.run_once()

    assert result["notices_delivered"] == 1
    assert published == ["in.(n1)"]


# AC17-H2 (happy): event notices carry the token notificationService requires
def test_notification_client_sends_the_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.notification_client import NotificationClient

    monkeypatch.setenv("NOTIFICATION_INTERNAL_TOKEN", "secret")
    seen: list[dict] = []

    def record(url, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(kwargs)
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.notification_client.httpx.post", record)

    NotificationClient(NOTICE_URL).notify_coordinator_assigned(
        event_request_id="e1", coordinator_id="c1", assigned_by="l1"
    )

    assert seen[0]["headers"] == {"X-Internal-Token": "secret"}
