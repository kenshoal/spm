"""Opt-in actual notificationService HTTP acceptance, with memory storage and fake inbox auth."""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from test_arrangement_review_notification_relay import (
    PreparedRepository,
    attempt,
    uid,
)

from app.services.arrangement_review_notification_relay import (
    ArrangementReviewNotificationRelay,
)
from app.services.notification_client import NotificationClient

RUNTIME = os.environ.get("SCRUM64_NOTIFICATION_RUNTIME")


@pytest.fixture
def real_notification_service(tmp_path):
    if not RUNTIME:
        pytest.skip("opt-in: set SCRUM64_NOTIFICATION_RUNTIME to notificationService's installed Python")
    service = Path(__file__).resolve().parents[2] / "notificationService"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    source = '''
from fastapi import Header
from app.auth import get_current_user_id
from app.main import create_app
from fakes import FakeNotificationRepository
import uvicorn
application = create_app(FakeNotificationRepository())
def fixture_inbox_identity(authorization: str = Header()):
    return authorization.removeprefix("Bearer ")
application.dependency_overrides[get_current_user_id] = fixture_inbox_identity
uvicorn.run(application, host="127.0.0.1", port=PORT, log_level="warning")
'''.replace("PORT", str(port))
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join([str(service), str(service / "tests")])}
    base = f"http://127.0.0.1:{port}"
    with (tmp_path / "notification-http.log").open("w") as log:
        process = subprocess.Popen([RUNTIME, "-c", source], cwd=service, env=environment, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail(f"notificationService fixture exited {process.returncode}; see {log.name}")
                try:
                    response = httpx.get(f"{base}/health", timeout=0.2)
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            else:
                pytest.fail("notificationService fixture did not become healthy")
            yield base
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


# AC3-X5 (cross-cutting): the real receiver accepts the producer payload over HTTP and deduplicates retry per recipient/event.
def test_real_notification_http_acceptance_and_retry_dedup(real_notification_service):
    current = attempt(coordinator=uid(10), staff=[uid(10), uid(11)])
    repository = PreparedRepository({uid(1): [current, current]}, {uid(1): [True, True]})
    relay = ArrangementReviewNotificationRelay(
        repository, NotificationClient(f"{real_notification_service}/notifications/events")
    )
    assert relay.relay_once() == 1
    original = {}
    for recipient in (uid(10), uid(11)):
        response = httpx.get(f"{real_notification_service}/notifications", headers={"Authorization": f"Bearer {recipient}"})
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "arrangement_needs_review"
        assert rows[0]["payload"] == current["payload"]
        original[recipient] = rows
    assert original[uid(10)][0]["id"] != original[uid(11)][0]["id"]
    # Simulates a sender crash before its acceptance record persisted; real receiver must absorb the repeated HTTP delivery.
    assert relay.relay_once() == 1
    assert len(repository.accepted) == 4
    for recipient, rows in original.items():
        response = httpx.get(f"{real_notification_service}/notifications", headers={"Authorization": f"Bearer {recipient}"})
        assert response.status_code == 200
        assert response.json() == rows
