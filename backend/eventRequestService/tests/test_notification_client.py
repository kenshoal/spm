import httpx
import pytest

from app.services.notification_client import NotificationClient


# AC2-N1 (negative): No Notification System exists yet — unconfigured must never attempt a call.
def test_noop_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("httpx.post should not be called when unconfigured")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    NotificationClient(None).notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )


# AC2-H1 (happy): Confirms the payload shape matches the original NotificationOutbox design.
def test_posts_expected_payload_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient("https://notifications.example.com/events").notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )

    assert captured["url"] == "https://notifications.example.com/events"
    assert captured["json"] == {
        "event_type": "coordinator_assigned",
        "recipient_id": "coord-1",
        "payload": {
            "event_request_id": "req-1",
            "coordinator_id": "coord-1",
            "assigned_by": "ops-1",
        },
    }


# AC2-N1 (negative): A network failure must be logged, never raised — it can't be allowed
# to fail the assignment it's reporting on.
def test_connection_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient("https://notifications.example.com/events").notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )


# AC2-N1 (negative): A non-2xx response must also be swallowed, not just a connection failure.
def test_error_response_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://notifications.example.com/events"
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: httpx.Response(
            500, json={"error": "boom"}, request=httpx.Request("POST", url)
        ),
    )

    NotificationClient("https://notifications.example.com/events").notify_coordinator_assigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )


SUBMITTED_PAYLOAD = {
    "event_request_id": "req-1",
    "organiser_id": "org-1",
    "status": "Submitted",
}


# AC1-H1 (happy): The Organiser's submission confirmation (SCRUM-37 AC1) carries the outbox
# event id, which notificationService uses to store a re-sent event only once.
def test_submission_posts_organiser_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(202, json={"status": "accepted"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    delivered = NotificationClient(
        "https://notifications.example.com/events"
    ).notify_event_request_submitted(
        event_id="outbox-1", organiser_id="org-1", payload=SUBMITTED_PAYLOAD
    )

    assert delivered is True
    assert captured["url"] == "https://notifications.example.com/events"
    assert captured["json"] == {
        "event_type": "event_request_submitted",
        "recipient_id": "org-1",
        "event_id": "outbox-1",
        "payload": {
            "event_request_id": "req-1",
            "organiser_id": "org-1",
            "status": "Submitted",
        },
    }


# AC1-N1 (negative): A failed delivery is reported, not raised, so the outbox row stays
# unpublished and is retried instead of being marked as sent.
@pytest.mark.parametrize(
    "outcome",
    [httpx.ConnectError("connection refused"), 500],
    ids=["unreachable", "error-response"],
)
def test_submission_reports_failed_delivery(
    monkeypatch: pytest.MonkeyPatch, outcome: object
) -> None:
    url = "https://notifications.example.com/events"

    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    delivered = NotificationClient(url).notify_event_request_submitted(
        event_id="outbox-1", organiser_id="org-1", payload=SUBMITTED_PAYLOAD
    )

    assert delivered is False


# AC1-N2 (negative): Unconfigured means nothing was delivered — reporting success here would
# let the relay mark events as sent that nobody received.
def test_submission_unconfigured_reports_not_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("httpx.post should not be called when unconfigured")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    delivered = NotificationClient(None).notify_event_request_submitted(
        event_id="outbox-1", organiser_id="org-1", payload=SUBMITTED_PAYLOAD
    )

    assert delivered is False


# AC4-H2 (happy): the old coordinator's notice is posted in the agreed shape, addressed to them
def test_posts_coordinator_unassigned_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(202, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient("https://notifications.example.com/events").notify_coordinator_unassigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )

    assert captured["url"] == "https://notifications.example.com/events"
    assert captured["json"] == {
        "event_type": "coordinator_unassigned",
        "recipient_id": "coord-1",
        "payload": {
            "event_request_id": "req-1",
            "coordinator_id": "coord-1",
            "assigned_by": "ops-1",
        },
    }


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("connection refused"),
        httpx.Response(500, json={"error": "boom"}, request=httpx.Request("POST", "https://n.example/e")),
    ],
    ids=["AC4-N3-connect", "AC4-N3-500"],
)
# AC4-N3 (negative): a failed unassigned notice is logged, never raised, so the reassignment stands
def test_unassigned_notice_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        if isinstance(failure, Exception):
            raise failure
        return failure  # type: ignore[return-value]

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient("https://n.example/e").notify_coordinator_unassigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )


# AC4-N3 (negative): with no notification service configured, nothing is sent and nothing fails
def test_unassigned_notice_is_a_no_op_without_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not post without a configured URL")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    NotificationClient(None).notify_coordinator_unassigned(
        event_request_id="req-1", coordinator_id="coord-1", assigned_by="ops-1"
    )


# AC5-H1 (happy): the technical-support assignment notice names the event and
# the requirement, and carries the assignment id so notificationService can
# dedupe retries
def test_technical_support_assignment_posts_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(202, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient("https://notifications.example.com/events").notify_technical_support_assigned(
        event_request_id="req-1",
        event_name="Tech Summit 2030",
        requirement_id="req-av-1",
        skill_tag="audio_visual",
        staff_id="tss-av",
        assigned_by="coord-1",
        assignment_id="assign-1",
    )

    assert captured["url"] == "https://notifications.example.com/events"
    assert captured["json"] == {
        "event_type": "technical_support_assigned",
        "recipient_id": "tss-av",
        "event_id": "assign-1",
        "payload": {
            "event_request_id": "req-1",
            "event_name": "Tech Summit 2030",
            "requirement_id": "req-av-1",
            "skill_tag": "audio_visual",
            "assigned_by": "coord-1",
        },
    }


# AC5-N2 (negative): a failed notice is logged naming the staff member and the
# event, never raised — the assignment it reports on must stand
@pytest.mark.parametrize(
    "outcome",
    [
        httpx.ConnectError("connection refused"),
        httpx.Response(500, json={"error": "boom"}, request=httpx.Request("POST", "https://n.example/e")),
    ],
    ids=["AC5-N2-connect", "AC5-N2-500"],
)
def test_technical_support_notice_failure_is_swallowed_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, outcome: object
) -> None:
    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[return-value]

    monkeypatch.setattr(httpx, "post", fake_post)

    with caplog.at_level("WARNING"):
        NotificationClient("https://n.example/e").notify_technical_support_assigned(
            event_request_id="req-1",
            event_name="Tech Summit 2030",
            requirement_id="req-av-1",
            skill_tag="audio_visual",
            staff_id="tss-av",
            assigned_by="coord-1",
            assignment_id="assign-1",
        )

    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "tss-av" in warnings[0].getMessage()
    assert "req-1" in warnings[0].getMessage()


# AC5-X1a (cross-cutting): with no notification service configured nothing is
# sent and nothing fails
def test_technical_support_notice_is_a_no_op_without_a_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not post without a configured URL")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    NotificationClient(None).notify_technical_support_assigned(
        event_request_id="req-1",
        event_name="Tech Summit 2030",
        requirement_id="req-av-1",
        skill_tag="audio_visual",
        staff_id="tss-av",
        assigned_by="coord-1",
        assignment_id="assign-1",
    )
