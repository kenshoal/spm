# SCRUM-57 (docs/testcases/scrum_57_testcases.md): the real settings lookup, address
# lookup and SMTP mailer behind Delivery. AC numbers are that story's.
import logging
import smtplib
from email.message import EmailMessage
from typing import Any, ClassVar, Self

import httpx2
import pytest
from fakes import (
    FakeAddressBook,
    FakeChannelSettings,
    FakeNotificationRepository,
    make_client,
)
from fastapi.testclient import TestClient

from app.adapters import (
    DirectoryError,
    MailNotConfigured,
    SmtpMailer,
    SupabaseAddressBook,
    SupabaseChannelSettings,
    UnconfiguredMailer,
    build_mailer,
)
from app.config import Settings
from app.delivery import Delivery

URL = "https://project.supabase.co"
USER_ID = "5b0c7a52-3a8e-4d0f-9f3e-2f6c1d9b8a10"


def settings_store(handler: Any) -> SupabaseChannelSettings:
    return SupabaseChannelSettings(
        URL, "sb_secret_test", transport=httpx2.MockTransport(handler)
    )


def address_book(handler: Any) -> SupabaseAddressBook:
    return SupabaseAddressBook(
        URL, "sb_secret_test", transport=httpx2.MockTransport(handler)
    )


def mail_settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        supabase_url=URL,
        supabase_secret_key="sb_secret_test",
        **overrides,
    )


# AC2-H1 (happy): the channel is read from notification_channel_settings for that type
def test_reads_the_channel_for_a_type() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["apikey"] = request.headers.get("apikey")
        return httpx2.Response(200, json=[{"channel": "both"}])

    assert settings_store(handler).channel_for("clarification_requested") == "both"
    assert seen == {
        "path": "/rest/v1/notification_channel_settings",
        "params": {
            "event_type": "eq.clarification_requested",
            "select": "channel",
            "limit": "1",
        },
        "apikey": "sb_secret_test",
    }


# AC2-P4 (partition): a type with no row is delivered in-app only
def test_a_type_with_no_setting_is_in_app() -> None:
    store = settings_store(lambda request: httpx2.Response(200, json=[]))

    assert store.channel_for("coordinator_assigned") == "in_app"


# AC2-N2 (negative): a store failure is raised, so Delivery can log it, not hidden as in_app
def test_a_settings_failure_is_raised() -> None:
    store = settings_store(lambda request: httpx2.Response(500, json={}))

    with pytest.raises(DirectoryError):
        store.channel_for("coordinator_assigned")


# AC3-H1 (happy): the address comes from the user's Supabase Auth account
def test_finds_the_email_of_a_user() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["apikey"] = request.headers.get("apikey")
        return httpx2.Response(200, json={"id": USER_ID, "email": "a@test.local"})

    assert address_book(handler).email_for(USER_ID) == "a@test.local"
    assert seen == {
        "path": f"/auth/v1/admin/users/{USER_ID}",
        "apikey": "sb_secret_test",
    }


# AC3-N3 (negative): an unknown user, a user with no email, and an id that is not a
# user id all mean "no address", without calling Supabase for the last
@pytest.mark.parametrize(
    ("recipient", "response"),
    [
        (USER_ID, httpx2.Response(404, json={})),
        (USER_ID, httpx2.Response(200, json={"id": USER_ID, "email": ""})),
        (USER_ID, httpx2.Response(200, json={"id": USER_ID})),
        ("coord-1", None),
    ],
    ids=["unknown-user", "blank-email", "no-email", "not-a-user-id"],
)
def test_no_address_found(recipient: str, response: httpx2.Response | None) -> None:
    calls: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.url.path)
        assert response is not None
        return response

    assert address_book(handler).email_for(recipient) is None
    assert (calls == []) == (response is None)


# AC3-N5 (negative): an auth outage is raised, so Delivery logs it and skips the email
def test_an_address_lookup_failure_is_raised() -> None:
    book = address_book(lambda request: httpx2.Response(500, json={}))

    with pytest.raises(DirectoryError):
        book.email_for(USER_ID)


class FakeSmtp:
    """Records what SmtpMailer does to an SMTP connection."""

    instances: ClassVar[list["FakeSmtp"]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.logged_in: tuple[str, str] | None = None
        self.message: EmailMessage | None = None
        FakeSmtp.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, message: EmailMessage) -> None:
        self.message = message


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    return FakeSmtp


# AC3-H1 (happy): the message goes through the configured server, encrypted and signed in,
# to one recipient, from the configured sender
def test_smtp_mailer_sends_one_message(fake_smtp: type[FakeSmtp]) -> None:
    mailer = SmtpMailer(
        mail_settings(
            smtp_host="smtp.test.local",
            smtp_port=2525,
            smtp_user="mailer",
            smtp_password="s3cret",
            mail_from="SPM <spm@test.local>",
        )
    )

    mailer.send(to="a@test.local", subject="Hello", body="Body text")

    [smtp] = fake_smtp.instances
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.test.local", 2525, 10)
    assert smtp.calls == ["starttls", "quit"]
    assert smtp.logged_in == ("mailer", "s3cret")
    assert smtp.message is not None
    assert smtp.message["To"] == "a@test.local"
    assert smtp.message["From"] == "SPM <spm@test.local>"
    assert smtp.message["Subject"] == "Hello"
    assert smtp.message.get_content().strip() == "Body text"
    assert smtp.message["Cc"] is None
    assert smtp.message["Bcc"] is None


# AC3-P3 (partition): a server that needs no login and no encryption is used as given
def test_smtp_mailer_skips_login_and_tls_when_not_configured(
    fake_smtp: type[FakeSmtp],
) -> None:
    mailer = SmtpMailer(mail_settings(smtp_host="localhost", smtp_starttls=False))

    mailer.send(to="a@test.local", subject="Hi", body="Body")

    [smtp] = fake_smtp.instances
    assert smtp.calls == ["quit"]
    assert smtp.logged_in is None


# AC3-N4 (negative): with no SMTP host the service still starts, and an email attempt is
# logged and leaves the stored notification and the 202 alone
def test_missing_mail_settings_do_not_break_the_action(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = mail_settings()
    assert settings.smtp_host is None
    assert isinstance(build_mailer(settings), UnconfiguredMailer)
    repository = FakeNotificationRepository()
    delivery = Delivery(
        channels=FakeChannelSettings({"clarification_requested": "email"}),
        addresses=FakeAddressBook({"organiser-1": "o@test.local"}),
        mailer=build_mailer(settings),
        inbox_url=settings.inbox_url,
    )
    with caplog.at_level(logging.WARNING), make_client(repository, delivery) as client:
        response = client.post(
            "/notifications/events",
            json={
                "event_id": "ev-1",
                "event_type": "clarification_requested",
                "recipient_id": "organiser-1",
            },
        )

    assert response.status_code == 202
    assert len(repository.rows) == 1
    assert "SMTP host is not set" in caplog.text


# AC3-N4 (negative): the unconfigured mailer says why, instead of pretending to send
def test_the_unconfigured_mailer_refuses_to_send() -> None:
    with pytest.raises(MailNotConfigured, match="SMTP host is not set"):
        UnconfiguredMailer().send(to="a@test.local", subject="s", body="b")


# AC3-P4 (partition): a configured host selects the SMTP mailer
def test_a_configured_host_selects_the_smtp_mailer() -> None:
    assert isinstance(
        build_mailer(mail_settings(smtp_host="smtp.test.local")), SmtpMailer
    )


# AC3-H1 (happy): the running service builds its delivery from its settings, so a
# configured type is emailed without the caller changing anything
def test_the_service_emails_through_the_delivery_built_from_its_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fakes import FakeMailer

    from app import main

    repository = FakeNotificationRepository()
    mailer = FakeMailer()
    built: list[Settings] = []

    def fake_build(settings: Settings) -> Delivery:
        built.append(settings)
        return Delivery(
            channels=FakeChannelSettings({"clarification_requested": "email"}),
            addresses=FakeAddressBook({"organiser-1": "o@test.local"}),
            mailer=mailer,
            inbox_url=settings.inbox_url,
        )

    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        main.SupabaseNotificationRepository,
        "from_settings",
        classmethod(lambda cls, settings: repository),
    )
    monkeypatch.setattr(main, "build_delivery", fake_build)
    main.get_settings.cache_clear()
    try:
        with TestClient(main.create_app()) as client:
            response = client.post(
                "/notifications/events",
                json={
                    "event_id": "ev-1",
                    "event_type": "clarification_requested",
                    "recipient_id": "organiser-1",
                },
                headers={"X-Internal-Token": "test-internal-token"},
            )
    finally:
        main.get_settings.cache_clear()

    assert response.status_code == 202
    assert len(built) == 1
    assert [message["to"] for message in mailer.sent] == ["o@test.local"]
