"""SCRUM-38: registration notices.

Case IDs match docs/testcases/scrum_38_testcases.md. The repository is faked
(see registration_support.py); the database function is proven elsewhere.
"""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from registration_support import (
    ATTENDEE_A,
    ATTENDEE_B,
    NON_CONFIRMED,
    FakeRegistrationRepository,
    add_event,
    fill,
    make_client,
)

from app.services.notification_client import NotificationClient
from app.services.registration_service import RegistrationService

NOTIFICATIONS_URL = "https://notifications.example.com/events"


class SpyNotificationClient:
    """Records registration notices without sending anything."""

    def __init__(self) -> None:
        self.confirmed: list[dict[str, Any]] = []
        self.full: list[dict[str, Any]] = []

    def notify_registration_confirmed(self, **kwargs: Any) -> None:
        self.confirmed.append(kwargs)

    def notify_registration_full(self, **kwargs: Any) -> None:
        self.full.append(kwargs)


def spy_client(repo: FakeRegistrationRepository, spy: Any):
    client = make_client(repo)
    client.app.state.registration_service = RegistrationService(repo, notification_client=spy)
    return client


def register_path(event_id: str) -> str:
    return f"/attendee/events/{event_id}/registrations"


# AC1-H1 (happy): Registering tells the Attendee, once the registration is saved.
def test_registering_notifies_the_attendee() -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    [registration] = repo.registrations
    assert spy.confirmed == [
        {
            "event_request_id": event_id,
            "attendee_id": ATTENDEE_A,
            "event_name": "Community Dinner",
            "registration_id": registration["id"],
        }
    ]


@pytest.mark.parametrize(
    ("setup", "expected_status"),
    [
        ("full", 409),
        ("closed", 409),
        ("already", 409),
        ("not_confirmed", 404),
    ],
    ids=["AC1-N1a", "AC1-N1b", "AC1-N1c", "AC1-N1d"],
)
# AC1-N1 (negative): A refused registration (full, closed, already registered, not
# Confirmed) changes nothing and tells nobody.
def test_refused_registration_notifies_nobody(setup: str, expected_status: int) -> None:
    repo = FakeRegistrationRepository()
    if setup == "closed":
        event_id = add_event(repo, registration_opens_at=None)
    elif setup == "not_confirmed":
        event_id = add_event(repo, status=NON_CONFIRMED[0])
    else:
        event_id = add_event(repo, registration_capacity=2)
    if setup == "full":
        fill(repo, event_id, 2)
    if setup == "already":
        repo.registrations.append(
            {
                "id": "existing",
                "event_request_id": event_id,
                "attendee_id": ATTENDEE_A,
                "status": "Registered",
                "created_at": None,
            }
        )
    spy = SpyNotificationClient()
    before = len(repo.registrations)

    with spy_client(repo, spy) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == expected_status
    assert len(repo.registrations) == before
    assert spy.confirmed == []


# AC1-N2 (negative): An unreachable notification service never blocks registration.
def test_notification_outage_does_not_block_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeRegistrationRepository()
    event_id = add_event(repo)

    def unreachable(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", unreachable)

    with spy_client(repo, NotificationClient(NOTIFICATIONS_URL)) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    assert len(repo.registrations) == 1


# AC1-H2 (happy): The client posts the confirmation to the Attendee in the agreed
# shape, with a stable key so a repeat is stored once.
def test_confirmed_notice_posts_the_agreed_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_registration_confirmed(
        event_request_id="event-1",
        attendee_id="attendee-1",
        event_name="Community Dinner",
        registration_id="reg-1",
    )

    assert captured["url"] == NOTIFICATIONS_URL
    assert captured["json"] == {
        "event_type": "registration_confirmed",
        "recipient_id": "attendee-1",
        "event_id": str(uuid5(NAMESPACE_URL, "registration-confirmed:reg-1")),
        "payload": {
            "event_request_id": "event-1",
            "event_name": "Community Dinner",
            "registration_id": "reg-1",
            "status": "Registered",
        },
    }


COORDINATOR = "coordinator-1"


def full_event(repo: FakeRegistrationRepository, registered: int, **overrides: Any) -> str:
    event_id = add_event(repo, registration_capacity=10, **overrides)
    repo.coordinators[event_id] = COORDINATOR
    fill(repo, event_id, registered)
    return event_id


def recipients(spy: SpyNotificationClient) -> list[str]:
    return sorted(notice["recipient_id"] for notice in spy.full)


# AC2-H1 (happy): The registration that takes the last place tells the Organiser and
# the assigned Coordinator, each once, and tells the Attendee only the AC1 notice.
def test_last_place_notifies_the_organiser_and_the_coordinator() -> None:
    repo = FakeRegistrationRepository()
    event_id = full_event(repo, registered=9)
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    [registration] = [r for r in repo.registrations if r["attendee_id"] == ATTENDEE_A]
    assert recipients(spy) == sorted(["organiser-1", COORDINATOR])
    assert all(
        notice
        == {
            "event_request_id": event_id,
            "recipient_id": notice["recipient_id"],
            "event_name": "Community Dinner",
            "registration_id": registration["id"],
            "capacity": 10,
        }
        for notice in spy.full
    )
    assert [c["attendee_id"] for c in spy.confirmed] == [ATTENDEE_A]


# AC2-B1 (boundary): One place short of full sends no full notice; the registration
# that takes the last place sends it.
def test_full_notice_only_when_the_last_place_is_taken() -> None:
    repo = FakeRegistrationRepository()
    event_id = full_event(repo, registered=8)
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        assert client.post(register_path(event_id)).status_code == 201
        assert spy.full == []
        client.app.dependency_overrides.clear()
    with spy_client(repo, spy) as other:
        from app.controllers import event_request_controller

        other.app.dependency_overrides[
            event_request_controller.get_authenticated_caller
        ] = lambda: event_request_controller.AuthenticatedCaller(
            id=ATTENDEE_B, roles=("attendee",)
        )
        assert other.post(register_path(event_id)).status_code == 201

    assert recipients(spy) == sorted(["organiser-1", COORDINATOR])


# AC2-N1 (negative): A refused registration on an already full event sends no full
# notice.
def test_refused_registration_on_a_full_event_notifies_nobody() -> None:
    repo = FakeRegistrationRepository()
    event_id = full_event(repo, registered=10)
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 409
    assert spy.full == []
    assert spy.confirmed == []


# AC2-P1 (partition): With no Coordinator assigned only the Organiser is told.
def test_no_coordinator_means_only_the_organiser_is_told() -> None:
    repo = FakeRegistrationRepository()
    event_id = full_event(repo, registered=9)
    repo.coordinators.clear()
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    assert recipients(spy) == ["organiser-1"]


# AC2-N2 (negative): A failed Coordinator lookup does not stop the Organiser's notice
# or undo the registration.
def test_coordinator_lookup_failure_does_not_block_registration() -> None:
    repo = FakeRegistrationRepository()
    event_id = full_event(repo, registered=9)
    repo.coordinator_lookup_fails = True
    spy = SpyNotificationClient()

    with spy_client(repo, spy) as client:
        response = client.post(register_path(event_id))

    assert response.status_code == 201
    assert recipients(spy) == ["organiser-1"]
    assert len(repo.registrations) == 10


# AC2-H2 (happy): The client posts the full notice to each recipient in the agreed
# shape, with a key per registration and recipient.
def test_full_notice_posts_the_agreed_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        captured["json"] = kwargs.get("json")
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    NotificationClient(NOTIFICATIONS_URL).notify_registration_full(
        event_request_id="event-1",
        recipient_id="organiser-1",
        event_name="Community Dinner",
        registration_id="reg-1",
        capacity=10,
    )

    assert captured["json"] == {
        "event_type": "registration_full",
        "recipient_id": "organiser-1",
        "event_id": str(uuid5(NAMESPACE_URL, "registration-full:reg-1:organiser-1")),
        "payload": {
            "event_request_id": "event-1",
            "event_name": "Community Dinner",
            "registration_id": "reg-1",
            "capacity": 10,
        },
    }
