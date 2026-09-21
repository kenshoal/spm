"""Notification hook tests use fake HTTP calls; no real alerts are sent."""

import logging

import httpx
import pytest

from app.block_models import VenueBlock
from app.config import Settings
from app.notification_client import NotificationClient, get_notification_client


@pytest.fixture
def block():
    return VenueBlock(
        id="block-1",
        venue_id="venue-1",
        created_by="staff-1",
        start_date="2026-10-01",
        end_date="2026-10-02",
        slots=["PM", "AM"],
        reason_category="maintenance",
        reason_detail="Air-conditioning repairs",
    )


def settings(url=None):
    return Settings(
        _env_file=None,
        venue_storage_backend="memory",
        venue_environment="development",
        supabase_url=None,
        supabase_secret_key=None,
        venue_dev_staff_user_id=None,
        notification_service_url=url,
    )


def test_unconfigured_client_makes_no_http_call(monkeypatch, block):
    def unexpected(*args, **kwargs):
        pytest.fail("A disabled notification hook must not send a request")

    monkeypatch.setattr(httpx, "post", unexpected)
    get_notification_client(settings()).notify_venue_block_applied(
        block=block, event_request_id="event-1", coordinator_id="coordinator-1"
    )


def test_configured_client_posts_team_envelope_and_block_details(monkeypatch, block):
    calls = []
    url = "https://notifications.example.com/events"

    def post(target, **kwargs):
        calls.append((target, kwargs))
        return httpx.Response(202, request=httpx.Request("POST", target))

    monkeypatch.setattr(httpx, "post", post)
    get_notification_client(settings(url)).notify_venue_block_applied(
        block=block, event_request_id="event-1", coordinator_id="coordinator-1"
    )
    assert calls == [
        (
            url,
            {
                "timeout": 5,
                "json": {
                    "event_type": "venue_block_applied",
                    "recipient_id": "coordinator-1",
                    "payload": {
                        "event_request_id": "event-1",
                        "coordinator_id": "coordinator-1",
                        "block_id": "block-1",
                        "venue_id": "venue-1",
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-02",
                        "slots": ["AM", "PM"],
                        "reason_category": "maintenance",
                        "reason_detail": "Air-conditioning repairs",
                        "created_by": "staff-1",
                    },
                },
            },
        )
    ]


@pytest.mark.parametrize("failure", ["connection", "timeout", "http"])
def test_delivery_failure_logged_without_raising_or_mutating_block(
    monkeypatch, caplog, block, failure
):
    url = "https://notifications.example.com/events?token=secret-value"
    before = block.model_dump()

    def post(target, **kwargs):
        if failure == "connection":
            raise httpx.ConnectError(target)
        if failure == "timeout":
            raise httpx.ReadTimeout(target)
        return httpx.Response(
            500, text="private-response", request=httpx.Request("POST", target)
        )

    monkeypatch.setattr(httpx, "post", post)
    with caplog.at_level(logging.WARNING):
        NotificationClient(url).notify_venue_block_applied(
            block=block, event_request_id="event-1", coordinator_id="coordinator-1"
        )
    assert "Failed to notify coordinator coordinator-1" in caplog.text
    assert "secret-value" not in caplog.text
    assert "private-response" not in caplog.text
    assert block.model_dump() == before


def test_dependency_creation_does_not_send_notification(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: pytest.fail("Unexpected request")
    )
    assert isinstance(
        get_notification_client(settings("https://notifications.example.com/events")),
        NotificationClient,
    )
