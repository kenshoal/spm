"""SCRUM-22 AC5: the Attendee is told when a withdrawal is saved.

Follow-up to SCRUM-22, split from SCRUM-38 AC1 ("the confirmation of a withdrawal
is SCRUM-22's registration_withdrawn"). Case IDs match
docs/testcases/scrum_22_testcases.md. The repository is faked (see
registration_support.py).
"""

from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
    NOW,
    FakeRegistrationRepository,
    add_event,
    add_registration,
    make_client,
)

from app.services.notification_client import NotificationClient
from app.services.registration_service import RegistrationService

NOTIFICATIONS_URL = "https://notifications.example.com/events"


class SpyNotificationClient:
    """Records withdrawal notices without sending anything."""

    def __init__(self) -> None:
        self.withdrawn: list[dict[str, Any]] = []

    def notify_registration_withdrawn(self, **kwargs: Any) -> None:
        self.withdrawn.append(kwargs)


def spy_client(repo: FakeRegistrationRepository, spy: Any, caller_id: str = ATTENDEE_A):
    client = make_client(repo, caller_id=caller_id)
    client.app.state.registration_service = RegistrationService(
        repo, notification_client=spy
    )
    return client


def withdraw_path(registration_id: str) -> str:
    return f"/attendee/registrations/{registration_id}/withdrawal"


# AC5-H1 (happy): withdrawing tells the Attendee, once the withdrawal is saved
def test_withdrawing_notifies_the_attendee() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    registration_id = add_registration(repo, event_id, ATTENDEE_A)
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 200
    assert spy.withdrawn == [
        {
            "event_request_id": event_id,
            "attendee_id": ATTENDEE_A,
            "event_name": "Community Dinner",
            "registration_id": registration_id,
        }
    ]
    assert repo.registrations[0]["status"] == "Withdrawn"


@pytest.mark.parametrize(
    ("case", "expected_status"),
    [
        ("not_owner", 404),
        ("unknown", 404),
        ("already_withdrawn", 409),
        ("started", 409),
        ("not_confirmed", 409),
    ],
)
# AC5-N1 (negative): a refused withdrawal changes nothing and tells nobody
def test_refused_withdrawal_notifies_nobody(case: str, expected_status: int) -> None:
    repo = FakeRegistrationRepository()
    event_overrides: dict[str, Any] = {}
    if case == "started":
        event_overrides["proposed_date_times"] = [NOW - timedelta(seconds=1)]
    if case == "not_confirmed":
        event_overrides["status"] = "Cancelled"
    event_id = add_event(repo, **event_overrides)
    owner = ATTENDEE_B if case == "not_owner" else ATTENDEE_A
    extra = {"status": "Withdrawn", "withdrawn_at": NOW} if case == "already_withdrawn" else {}
    registration_id = add_registration(repo, event_id, owner, **extra)
    target = "00000000-0000-4000-8000-000000000000" if case == "unknown" else registration_id
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(withdraw_path(target))

    assert response.status_code == expected_status
    assert spy.withdrawn == []


# AC5-N2 (negative): an unreachable notification service never undoes a withdrawal
def test_notification_outage_does_not_block_withdrawal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_post(url: str, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", failing_post)
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    registration_id = add_registration(repo, event_id, ATTENDEE_A)
    client = make_client(repo)
    client.app.state.registration_service = RegistrationService(
        repo, notification_client=NotificationClient(NOTIFICATIONS_URL)
    )

    with client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 200
    assert response.json()["status"] == "Withdrawn"
    assert repo.registrations[0]["status"] == "Withdrawn"


# AC5-H2 (happy): the client posts the withdrawal to the Attendee in the agreed
# shape, with a stable key per registration so a repeat is stored once.
def test_withdrawn_notice_posts_the_agreed_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        assert url == NOTIFICATIONS_URL
        sent.append(kwargs["json"])
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = NotificationClient(NOTIFICATIONS_URL)

    client.notify_registration_withdrawn(
        event_request_id="event-1",
        attendee_id="attendee-1",
        event_name="Community Dinner",
        registration_id="reg-1",
    )

    assert sent == [
        {
            "event_type": "registration_withdrawn",
            "recipient_id": "attendee-1",
            "event_id": str(uuid5(NAMESPACE_URL, "registration-withdrawn:reg-1")),
            "payload": {
                "event_request_id": "event-1",
                "event_name": "Community Dinner",
                "registration_id": "reg-1",
                "status": "Withdrawn",
            },
        }
    ]


# AC5-B1 (boundary): registering again after a withdrawal makes a new registration,
# so withdrawing that one is a new notice with a different key
def test_second_registration_withdrawal_uses_a_new_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys: list[str] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        keys.append(kwargs["json"]["event_id"])
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = NotificationClient(NOTIFICATIONS_URL)
    for registration_id in ("reg-1", "reg-2"):
        client.notify_registration_withdrawn(
            event_request_id="event-1",
            attendee_id="attendee-1",
            event_name=None,
            registration_id=registration_id,
        )

    assert len(keys) == 2
    assert keys[0] != keys[1]


# AC5-N3 (negative): a notice the service rejects is swallowed, not raised
def test_withdrawn_notice_error_response_is_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_registration_withdrawn(
        event_request_id="event-1",
        attendee_id="attendee-1",
        event_name="Community Dinner",
        registration_id="reg-1",
    )


# AC5-N4 (negative): with no notification service configured nothing is sent
def test_withdrawn_notice_is_a_no_op_without_a_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(url: str, **kwargs: object) -> httpx.Response:
        raise AssertionError("must not post without a URL")

    monkeypatch.setattr(httpx, "post", forbidden)

    NotificationClient(None).notify_registration_withdrawn(
        event_request_id="event-1",
        attendee_id="attendee-1",
        event_name=None,
        registration_id="reg-1",
    )


class StaleReadRepository(FakeRegistrationRepository):
    """Reads say the event is Confirmed, but the locked write finds it Cancelled."""

    def get_event(self, event_id):  # type: ignore[no-untyped-def]
        event = super().get_event(event_id)
        if event is not None:
            event["status"] = "Confirmed"
        return event


# AC5-N5 (negative): a withdrawal the database refuses after the early check passed
# (the event changed in between) tells nobody
def test_database_refusal_after_early_check_notifies_nobody() -> None:
    repo = StaleReadRepository()
    event_id = add_event(repo, status="Cancelled")
    registration_id = add_registration(repo, event_id, ATTENDEE_A)
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(withdraw_path(registration_id))

    assert response.status_code == 409
    assert repo.registrations[0]["status"] == "Registered"
    assert spy.withdrawn == []
