"""SCRUM-40 distinct transport, activation/lifespan and manual-command boundaries."""

import asyncio
import json
from datetime import UTC, datetime
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
)

from app import main as application
from app.config import PeriodicTaskSettings
from app.repositories import SupabaseEventRequestRepository
from app.services import auto_completion
from app.services.auto_completion import AutoCompletionService

E = "40000000-0000-4000-8000-000000000001"
MISSING = "40000000-0000-4000-8000-000000000002"
NOW = datetime(2026, 10, 23, 4, tzinfo=UTC)


# AC1-X6 (cross-cutting): actual adapter HTTP preserves Confirmed/keyset scope and exact native scalar/setter contracts without a client-side eligibility rule.
def test_real_adapter_sweep_and_setter_wire_contract():
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path.endswith("/event_requests"):
            params = dict(request.url.params)
            assert params == {
                "select": "id,final_event_end_at",
                "status": "eq.Confirmed",
                "order": "id.asc",
                "limit": "1000",
                **({"id": f"gt.{MISSING}"} if len(calls) > 1 else {}),
            }
            return httpx.Response(
                200,
                json=[]
                if len(calls) > 1
                else [
                    {"id": E, "final_event_end_at": "2026-10-16T03:59:59Z"},
                    {"id": MISSING, "final_event_end_at": None},
                ],
            )
        if request.url.path.endswith("/rpc/complete_overdue_event_request"):
            body = json.loads(request.content)
            assert body["p_event_request_id"] in {E, MISSING}
            assert body == {
                "p_event_request_id": body["p_event_request_id"],
                "p_as_of": NOW.isoformat(),
            }
            assert "vnd.pgrst.object" not in request.headers.get("accept", "")
            return httpx.Response(200, json=body["p_event_request_id"] == E)
        assert request.url.path.endswith("/rpc/set_event_request_final_end")
        assert json.loads(request.content) == {
            "p_event_request_id": E,
            "p_coordinator_id": "coord-1",
            "p_final_event_end_at": NOW.isoformat(),
        }
        assert request.headers["accept"] == "application/vnd.pgrst.object+json"
        return httpx.Response(
            200, json={"id": E, "final_event_end_at": NOW.isoformat()}
        )

    repository = SupabaseEventRequestRepository(
        "https://project.test", "test-server-key", transport=httpx.MockTransport(handle)
    )
    try:
        assert AutoCompletionService(repository).run_once(as_of=NOW) == {
            "examined": 2,
            "completed": 1,
            "unchanged": 0,
            "skipped_missing_end": 1,
            "failed": 0,
        }
        assert repository.complete_overdue_event_request(MISSING, NOW) is False
        assert repository.set_final_end(E, "coord-1", NOW) == {
            "id": E,
            "final_event_end_at": NOW.isoformat(),
        }
        assert [request.method for request in calls] == [
            "GET",
            "POST",
            "GET",
            "POST",
            "POST",
        ]
        assert all(
            request.headers["authorization"] == "Bearer test-server-key"
            for request in calls
        )
    finally:
        repository.close()


# AC1-X7 (cross-cutting): activation is disabled by default, independent of notification configuration and safely cancelled by the injected app lifespan.
def test_opt_in_settings_factory_and_injected_lifespan(monkeypatch):
    monkeypatch.delenv("AUTO_COMPLETION_ENABLED", raising=False)
    monkeypatch.delenv("PERIODIC_TASK_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("NOTIFICATION_SERVICE_URL", raising=False)
    defaults = PeriodicTaskSettings(_env_file=None)
    assert defaults.auto_completion_enabled is False
    assert defaults.periodic_task_interval_seconds == 60
    monkeypatch.setattr(application, "get_periodic_task_settings", lambda: defaults)
    assert application.build_periodic_task_runner() is None
    monkeypatch.setenv("AUTO_COMPLETION_ENABLED", "true")
    monkeypatch.setenv("PERIODIC_TASK_INTERVAL_SECONDS", "7")
    enabled = PeriodicTaskSettings(_env_file=None)
    assert (
        enabled.auto_completion_enabled is True
        and enabled.periodic_task_interval_seconds == 7
    )
    for value in ("0", "-1", "nan", "inf"):
        with pytest.raises(ValidationError):
            PeriodicTaskSettings(_env_file=None, periodic_task_interval_seconds=value)

    passes = []

    class PreparedCompletion:
        def run_once(self):
            passes.append("completion")

    monkeypatch.setattr(application, "get_periodic_task_settings", lambda: enabled)
    monkeypatch.setattr(
        application, "build_auto_completion_service", lambda: PreparedCompletion()
    )
    runner = application.build_periodic_task_runner()
    assert runner is not None
    runner.run_once()
    assert passes == ["completion"]

    entered, stopped = Event(), Event()

    class InjectedRunner:
        async def run_forever(self):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    events = FakeEventRequestRepository()
    app = application.create_app(
        events,
        FakeCoordinatorAssignmentRepository(events),
        periodic_task_runner=InjectedRunner(),
    )
    with TestClient(app):
        assert entered.wait(1), "injected timer never started"
        assert not stopped.is_set()
    assert stopped.is_set()
    # Ordinary injected test apps must not silently construct a production worker.
    monkeypatch.setattr(
        application,
        "build_periodic_task_runner",
        lambda: (_ for _ in ()).throw(AssertionError("implicit worker construction")),
    )
    with TestClient(
        application.create_app(events, FakeCoordinatorAssignmentRepository(events))
    ):
        pass


# AC1-X8 (cross-cutting): manual --once delegates the real clock to one service pass, reports counts and exposes failures through a nonzero exit with cleanup.
def test_manual_cli_single_pass_clock_failure_exit_and_cleanup(monkeypatch, capsys):
    reports = [
        {
            "examined": 1,
            "completed": 1,
            "unchanged": 0,
            "skipped_missing_end": 0,
            "failed": 0,
        },
        {
            "examined": 1,
            "completed": 0,
            "unchanged": 0,
            "skipped_missing_end": 0,
            "failed": 1,
        },
        RuntimeError("prepared pass failure"),
    ]
    class PreparedService:
        def __init__(self, report):
            self.report = report
            self.calls = []

        def run_once(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            if isinstance(self.report, Exception):
                raise self.report
            return self.report

        def close(self):
            self.calls.append("closed")

    for report, expected_exit in zip(reports, [0, 1, 1], strict=True):
        service = PreparedService(report)
        monkeypatch.setattr(
            auto_completion, "build_auto_completion_service", lambda service=service: service
        )
        assert auto_completion.main(["--once"]) == expected_exit
        captured = capsys.readouterr()
        assert service.calls == [((), {}), "closed"]
        if not isinstance(report, Exception):
            assert json.loads(captured.out) == report
