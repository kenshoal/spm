"""Endpoint-specific auth dependency checks; Auth HTTP is an explicit double."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from test_event_change_rejection import REASON, create_pending
from test_event_change_request import eligible_fixture

from app.controllers import event_request_controller as controller


# AC4-N5 (negative): missing bearer reaches the actual auth dependency and stops without Auth HTTP, notice or protected writes.
def test_missing_bearer_cannot_reject_pending_proposal(monkeypatch):
    client, events, event_id = eligible_fixture()
    with client:
        pending = create_pending(client, event_id)
        before = deepcopy((events.rows, events.change_request_rows))
        client.app.dependency_overrides.pop(controller.get_coordinator_id)
        client.app.dependency_overrides.pop(controller.get_authenticated_caller)
        network = Mock(side_effect=AssertionError("Missing bearer must not call another service"))
        monkeypatch.setattr(httpx, "get", network)
        monkeypatch.setattr(httpx, "post", network)
        response = client.post(
            f"/event-requests/{event_id}/change-requests/{pending['id']}/decision",
            json={"decision": "Rejected", "reason": REASON},
        )
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert (events.rows, events.change_request_rows) == before
    network.assert_not_called()


# AC4-N6 (negative): verified organiser ownership cannot grant coordinator rejection capability.
def test_organiser_cannot_reject_own_pending_proposal(monkeypatch):
    client, events, event_id = eligible_fixture()
    owner_id = "35000000-0000-4000-8000-000000000051"
    with client:
        pending = create_pending(client, event_id)
        events.rows[event_id]["organiser_id"] = owner_id
        events.change_request_rows[0]["organiser_id"] = owner_id
        before = deepcopy((events.rows, events.change_request_rows))
        client.app.dependency_overrides.pop(controller.get_coordinator_id)
        client.app.dependency_overrides.pop(controller.get_authenticated_caller)
        monkeypatch.setattr(controller, "get_settings", lambda: SimpleNamespace(auth_service_url="https://auth.test"))
        auth = Mock(return_value=httpx.Response(
            200, json={"id": owner_id, "roles": ["event_organiser"]},
            request=httpx.Request("GET", "https://auth.test/auth/me"),
        ))
        notices = Mock(side_effect=AssertionError("An organiser cannot trigger a rejection notice"))
        monkeypatch.setattr(httpx, "get", auth)
        monkeypatch.setattr(httpx, "post", notices)
        response = client.post(
            f"/event-requests/{event_id}/change-requests/{pending['id']}/decision",
            headers={"Authorization": "Bearer organiser-fixture-session"},
            json={"decision": "Rejected", "reason": REASON},
        )
    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert (events.rows, events.change_request_rows) == before
    auth.assert_called_once_with("https://auth.test/auth/me", headers={"Authorization": "Bearer organiser-fixture-session"}, timeout=10)
    notices.assert_not_called()
