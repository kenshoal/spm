"""Approval outcome notice through the existing public API; outbound HTTP is captured."""

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from test_change_rejection_notification import URL
from test_event_change_approval import CHANGES, approve, create_nondate_pending
from test_event_change_request import eligible_fixture

from app.config import get_settings


@pytest.fixture
def configured_approval(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SERVICE_URL", URL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# AC6-H2 (happy): a real saved approval announces only its stored organiser and immutable proposal identity after the commit boundary.
def test_saved_approval_notifies_owner_after_commit_once(configured_approval, monkeypatch):
    client, events, event_id = eligible_fixture()
    sent = []

    def post(url, **kwargs):
        assert events.change_request_rows[-1]["status"] == "Approved"
        assert all(events.rows[event_id][key] == value for key, value in CHANGES.items())
        sent.append((url, deepcopy(kwargs["json"])))
        return httpx.Response(202, json={"status": "accepted"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    with client:
        pending = create_nondate_pending(client, event_id)
        response = approve(client, event_id, pending["id"])
        assert response.status_code == 200, response.text
        assert sent == [(URL, {
            "event_type": "event_change_approved", "recipient_id": pending["organiser_id"],
            "event_id": str(uuid5(NAMESPACE_URL, f"event-change-approved:{pending['id']}")),
            "payload": {"event_request_id": event_id, "change_request_id": pending["id"], "reason": None},
        })]
        before = deepcopy((events.rows, events.change_request_rows))
        repeated = approve(client, event_id, pending["id"])
        assert repeated.status_code == 409
        assert repeated.json() == {"detail": f"Event request {event_id} cannot accept that change action"}
        assert (events.rows, events.change_request_rows) == before
        assert len(sent) == 1


@pytest.mark.parametrize("failure", ["http200", "unexpected"], ids=["AC6-N5", "AC6-N6"])
# AC6-N5, AC6-N6 (negative): neither non-202 acceptance nor an unexpected sender failure can mask the already saved approved plan.
def test_failed_approval_notice_preserves_saved_success(configured_approval, monkeypatch, caplog, failure):
    client, events, event_id = eligible_fixture()
    sent = []

    def post(url, **kwargs):
        assert events.change_request_rows[-1]["status"] == "Approved"
        sent.append(deepcopy(kwargs["json"]))
        if failure == "unexpected":
            raise RuntimeError("Prepared unexpected notification sender failure")
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    with client:
        pending = create_nondate_pending(client, event_id)
        response = approve(client, event_id, pending["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Approved"
    assert events.change_request_rows[0]["status"] == "Approved"
    assert all(events.rows[event_id][key] == value for key, value in CHANGES.items())
    assert len(sent) == 1
    assert sent[0]["event_type"] == "event_change_approved"
    assert caplog.records, "Failed delivery must be logged rather than claimed accepted"


# AC6-N7 (negative): an upstream Pending result is not a saved approval and must fail safely without announcing success or changing rows.
def test_pending_rpc_outcome_is_safe_upstream_failure_without_notice(configured_approval, monkeypatch):
    client, events, event_id = eligible_fixture()
    sent = []
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: sent.append(kwargs))
    with client:
        pending = create_nondate_pending(client, event_id)
        before = deepcopy((events.rows, events.change_request_rows))
        monkeypatch.setattr(events, "decide_change_request", lambda *args: deepcopy(events.change_request_rows[0]))
        response = approve(client, event_id, pending["id"])
    assert response.status_code == 502
    assert response.json() == {"detail": "Event change decision unavailable"}
    assert (events.rows, events.change_request_rows) == before
    assert sent == []
