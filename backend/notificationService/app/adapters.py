"""Real mail, settings and address lookups behind Delivery (SCRUM-57)."""

import smtplib
from email.message import EmailMessage
from uuid import UUID

import httpx2

from app.config import Settings
from app.delivery import Delivery

DEFAULT_CHANNEL = "in_app"
SMTP_TIMEOUT_SECONDS = 10


class MailNotConfigured(RuntimeError):
    """No SMTP host is set, so email cannot be sent."""


class DirectoryError(RuntimeError):
    """Supabase could not answer a settings or address lookup."""


def _supabase_client(
    base_url: str, secret_key: str, transport: httpx2.BaseTransport | None
) -> httpx2.Client:
    headers = {"apikey": secret_key}
    # Legacy service-role keys are JWTs; new sb_secret keys use apikey only.
    if not secret_key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {secret_key}"
    return httpx2.Client(
        base_url=base_url, headers=headers, timeout=10, transport=transport
    )


class SupabaseChannelSettings:
    """Reads public.notification_channel_settings (migration 0065)."""

    def __init__(
        self,
        supabase_url: str,
        secret_key: str,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._client = _supabase_client(
            f"{supabase_url.rstrip('/')}/rest/v1", secret_key, transport
        )

    def channel_for(self, event_type: str) -> str:
        try:
            response = self._client.get(
                "/notification_channel_settings",
                params={
                    "event_type": f"eq.{event_type}",
                    "select": "channel",
                    "limit": "1",
                },
            )
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise DirectoryError("Could not read the channel setting") from error
        rows = response.json()
        return rows[0]["channel"] if rows else DEFAULT_CHANNEL


class SupabaseAddressBook:
    """Finds a user's email address in their Supabase Auth account."""

    def __init__(
        self,
        supabase_url: str,
        secret_key: str,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._client = _supabase_client(
            f"{supabase_url.rstrip('/')}/auth/v1", secret_key, transport
        )

    def email_for(self, recipient_id: str) -> str | None:
        try:
            user_id = UUID(recipient_id)
        except ValueError:
            # Not a user id (callers also send ids like "coord-1" in tests).
            return None
        try:
            response = self._client.get(f"/admin/users/{user_id}")
            if response.status_code == httpx2.codes.NOT_FOUND:
                return None
            response.raise_for_status()
        except httpx2.HTTPError as error:
            raise DirectoryError("Could not look up the user's email") from error
        return response.json().get("email") or None


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._host = str(settings.smtp_host)
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = (
            settings.smtp_password.get_secret_value() if settings.smtp_password else None
        )
        self._starttls = settings.smtp_starttls
        self._sender = settings.mail_from

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(
            self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS
        ) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._user and self._password:
                smtp.login(self._user, self._password)
            smtp.send_message(message)


class UnconfiguredMailer:
    """Stands in when no SMTP host is set, so the reason shows up in the log."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        raise MailNotConfigured("SMTP host is not set; email was not sent")


def build_mailer(settings: Settings) -> SmtpMailer | UnconfiguredMailer:
    return SmtpMailer(settings) if settings.smtp_host else UnconfiguredMailer()


def build_delivery(settings: Settings) -> Delivery:
    url = str(settings.supabase_url)
    key = settings.supabase_secret_key.get_secret_value()
    return Delivery(
        channels=SupabaseChannelSettings(url, key),
        addresses=SupabaseAddressBook(url, key),
        mailer=build_mailer(settings),
        inbox_url=settings.inbox_url,
    )
