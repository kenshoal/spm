# SCRUM-57 (docs/testcases/scrum_57_testcases.md). The AC numbers below are that
# story's, not SCRUM-37's: AC2 is the per-type channel setting, AC3 is email.
import pytest
from fakes import (
    FakeAddressBook,
    FakeChannelSettings,
    FakeMailer,
    FakeNotificationRepository,
    make_client,
)

from app.delivery import Delivery

ENDPOINT = "/notifications/events"
ORGANISER = "organiser-1"
ORGANISER_EMAIL = "organiser@test.local"
COORDINATOR = "coord-1"
COORDINATOR_EMAIL = "coord@test.local"
INBOX_URL = "https://app.test.local/notifications"


def build(
    channels: dict[str, str] | None = None,
    addresses: dict[str, str] | None = None,
) -> tuple[FakeNotificationRepository, FakeMailer, Delivery]:
    repository = FakeNotificationRepository()
    mailer = FakeMailer()
    delivery = Delivery(
        channels=FakeChannelSettings(channels),
        addresses=FakeAddressBook(addresses),
        mailer=mailer,
        inbox_url=INBOX_URL,
    )
    return repository, mailer, delivery


def event(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "event_id": "ev-1",
        "event_type": "clarification_requested",
        "recipient_id": ORGANISER,
        "payload": {"event_request_id": "11111111-1111-4111-8111-111111111111"},
    }
    return body | overrides


# AC2-H1 (happy): a type set to email reaches the recipient by email, only to them
def test_an_email_type_is_sent_to_the_recipient_only() -> None:
    repository, mailer, delivery = build(
        channels={"clarification_requested": "email"},
        addresses={ORGANISER: ORGANISER_EMAIL, COORDINATOR: COORDINATOR_EMAIL},
    )
    with make_client(repository, delivery) as client:
        response = client.post(ENDPOINT, json=event())

    assert response.status_code == 202
    assert [message["to"] for message in mailer.sent] == [ORGANISER_EMAIL]
    assert len(repository.rows) == 1


# AC2-P1, AC2-P2, AC2-P4 (partition): in_app sends no email, both sends one, and a
# type with no setting behaves as in_app
@pytest.mark.parametrize(
    ("channel", "emails"),
    [("in_app", 0), ("both", 1), (None, 0)],
    ids=["AC2-P1", "AC2-P2", "AC2-P4"],
)
def test_the_channel_decides_whether_an_email_is_sent(
    channel: str | None, emails: int
) -> None:
    channels = {} if channel is None else {"clarification_requested": channel}
    repository, mailer, delivery = build(channels, {ORGANISER: ORGANISER_EMAIL})
    with make_client(repository, delivery) as client:
        response = client.post(ENDPOINT, json=event())

    assert response.status_code == 202
    assert len(mailer.sent) == emails
    assert len(repository.rows) == 1


# AC2-X1 (cross-cutting): a setting for one type does not change another type
def test_a_setting_applies_to_its_own_type_only() -> None:
    repository, mailer, delivery = build(
        {"clarification_requested": "both"}, {ORGANISER: ORGANISER_EMAIL}
    )
    with make_client(repository, delivery) as client:
        client.post(ENDPOINT, json=event(event_id="ev-a"))
        client.post(
            ENDPOINT, json=event(event_id="ev-b", event_type="coordinator_assigned")
        )

    assert len(repository.rows) == 2
    assert [message["subject"] for message in mailer.sent] == [
        "New notification: clarification_requested"
    ]


# AC2-N2 (negative): an unreadable setting falls back to in-app, never losing the
# notification or failing the caller
def test_an_unreadable_setting_falls_back_to_in_app(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository, mailer, delivery = build(
        {"clarification_requested": "email"}, {ORGANISER: ORGANISER_EMAIL}
    )
    delivery._channels.fail = True  # type: ignore[attr-defined]
    with make_client(repository, delivery) as client:
        response = client.post(ENDPOINT, json=event())

    assert response.status_code == 202
    assert len(repository.rows) == 1
    assert mailer.sent == []
    assert "settings store is down" in caplog.text


# AC3-H1 (happy): the email names the type, links to the inbox and goes to one person
def test_the_email_names_the_type_and_links_to_the_inbox() -> None:
    repository, mailer, delivery = build(
        {"clarification_requested": "both"}, {ORGANISER: ORGANISER_EMAIL}
    )
    with make_client(repository, delivery) as client:
        client.post(ENDPOINT, json=event())

    [message] = mailer.sent
    assert message["to"] == ORGANISER_EMAIL
    assert "clarification_requested" in message["subject"]
    assert INBOX_URL in message["body"]


# AC3-N1 (negative): a mail server failure does not fail the caller or undo the row
def test_a_mail_failure_keeps_the_notification_and_still_accepts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository, mailer, delivery = build(
        {"clarification_requested": "email"}, {ORGANISER: ORGANISER_EMAIL}
    )
    mailer.fail = True
    with make_client(repository, delivery) as client:
        response = client.post(ENDPOINT, json=event())

    assert response.status_code == 202
    assert len(repository.rows) == 1
    assert mailer.sent == []
    assert "mail server is down" in caplog.text


# AC3-N2 (negative): a retried event stores one row and sends one email
def test_a_retried_event_sends_no_second_email() -> None:
    repository, mailer, delivery = build(
        {"clarification_requested": "email"}, {ORGANISER: ORGANISER_EMAIL}
    )
    with make_client(repository, delivery) as client:
        first = client.post(ENDPOINT, json=event())
        retry = client.post(ENDPOINT, json=event())

    assert (first.status_code, retry.status_code) == (202, 202)
    assert len(repository.rows) == 1
    assert len(mailer.sent) == 1


# AC3-N3 (negative): a recipient with no address keeps the inbox row and gets no email
def test_a_recipient_without_an_address_is_not_emailed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository, mailer, delivery = build({"clarification_requested": "email"}, {})
    with make_client(repository, delivery) as client:
        response = client.post(ENDPOINT, json=event())

    assert response.status_code == 202
    assert len(repository.rows) == 1
    assert mailer.sent == []
    assert "no email address" in caplog.text


# AC3-P1 (partition): one event_id for two recipients emails each of them once
def test_the_same_event_id_emails_each_recipient_once() -> None:
    repository, mailer, delivery = build(
        {"clarification_requested": "email"},
        {ORGANISER: ORGANISER_EMAIL, COORDINATOR: COORDINATOR_EMAIL},
    )
    with make_client(repository, delivery) as client:
        client.post(ENDPOINT, json=event())
        client.post(ENDPOINT, json=event(recipient_id=COORDINATOR))

    assert len(repository.rows) == 2
    assert sorted(message["to"] for message in mailer.sent) == [
        COORDINATOR_EMAIL,
        ORGANISER_EMAIL,
    ]


# AC3-P2 (partition): a type with no known wording still gets a usable email
def test_an_unknown_type_gets_a_generic_email() -> None:
    repository, mailer, delivery = build(
        {"future_type": "email"}, {ORGANISER: ORGANISER_EMAIL}
    )
    with make_client(repository, delivery) as client:
        client.post(ENDPOINT, json=event(event_type="future_type"))

    [message] = mailer.sent
    assert message["subject"].strip() != ""
    assert INBOX_URL in message["body"]
