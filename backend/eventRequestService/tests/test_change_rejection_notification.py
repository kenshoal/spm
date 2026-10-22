"""SCRUM-35 organiser outcome contract through the public API and captured HTTP."""

from copy import deepcopy
from uuid import UUID

import httpx
import pytest
from test_event_change_rejection import REASON, create_pending, reject
from test_event_change_request import eligible_fixture

from app.config import get_settings
from app.repositories import EventRequestRpcError

URL = "https://notification.test/notifications/events"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SERVICE_URL", URL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# AC6-H1 (happy): notify the stored organiser only after the saved rejection, using a stable per-change identity and no repeat send.
def test_saved_rejection_notifies_owner_after_commit_with_stable_identity(configured, monkeypatch):
    client, events, event_id = eligible_fixture()
    captured = []

    def post(url, **kwargs):
        assert events.change_request_rows[-1]["status"] == "Rejected"
        captured.append((url, kwargs))
        return httpx.Response(202, json={"status": "accepted"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    with client:
        pending = create_pending(client, event_id)
        before = deepcopy(events.rows)
        response = reject(client, event_id, pending["id"])
        assert response.status_code == 200
        assert len(captured) == 1
        url, kwargs = captured[0]
        body = kwargs["json"]
        assert url == URL
        assert body == {
            "event_type": "event_change_rejected", "recipient_id": pending["organiser_id"],
            "event_id": body["event_id"],
            "payload": {"event_request_id": event_id, "change_request_id": pending["id"], "reason": REASON},
        }
        assert UUID(body["event_id"]).version == 5
        assert len(body["event_id"]) <= 64
        assert events.rows == before
        assert reject(client, event_id, pending["id"]).status_code == 409
        assert len(captured) == 1
        next_pending = create_pending(client, event_id)
        assert reject(client, event_id, next_pending["id"]).status_code == 200
        assert len(captured) == 2
        assert captured[1][1]["json"]["event_id"] != body["event_id"]


@pytest.mark.parametrize("failure", ["http502", "timeout", "http200"], ids=["AC6-N2-http502", "AC6-N4-timeout", "AC6-N2-http200"])
# AC6-N2, AC6-N4 (negative): an upstream rejection or transport outage cannot erase the successful decision; failed delivery is logged honestly.
def test_notification_failure_preserves_rejection(configured, monkeypatch, caplog, failure):
    client, events, event_id = eligible_fixture()
    attempts = []

    def post(url, **kwargs):
        assert events.change_request_rows[0]["status"] == "Rejected"
        attempts.append(kwargs["json"])
        if failure == "timeout":
            raise httpx.ReadTimeout("test upstream timeout")
        return httpx.Response(200 if failure == "http200" else 502, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    with client:
        pending = create_pending(client, event_id)
        before = deepcopy(events.rows)
        response = reject(client, event_id, pending["id"])
    assert response.status_code == 200
    assert response.json()["status"] == "Rejected"
    assert response.json()["decision_reason"] == REASON
    assert events.change_request_rows[0]["status"] == "Rejected"
    assert events.rows == before
    assert len(attempts) == 1
    assert attempts[0]["event_type"] == "event_change_rejected"
    assert caplog.records, "A failed delivery must be logged instead of presented as accepted"


# AC6-N3 (negative): a database refusal is never followed by an outcome notification or any protected write.
def test_refused_rejection_never_notifies(configured, monkeypatch):
    client, events, event_id = eligible_fixture()
    attempts = []
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: attempts.append(kwargs))
    with client:
        pending = create_pending(client, event_id)
        before = deepcopy((events.rows, events.change_request_rows))

        def refused(*args):
            raise EventRequestRpcError("test locked refusal", "P0004")

        monkeypatch.setattr(events, "decide_change_request", refused)
        response = reject(client, event_id, pending["id"])
    assert response.status_code == 409
    assert response.json() == {"detail": f"Event request {event_id} cannot accept that change action"}
    assert (events.rows, events.change_request_rows) == before
    assert attempts == []
