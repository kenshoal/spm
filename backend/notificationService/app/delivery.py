"""Delivery of a stored notification over the channels chosen for its type (SCRUM-57)."""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class ChannelSettings(Protocol):
    def channel_for(self, event_type: str) -> str: ...


class AddressBook(Protocol):
    def email_for(self, recipient_id: str) -> str | None: ...


class Mailer(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...


class Delivery:
    def __init__(
        self,
        *,
        channels: ChannelSettings,
        addresses: AddressBook,
        mailer: Mailer,
        inbox_url: str,
    ) -> None:
        self._channels = channels
        self._addresses = addresses
        self._mailer = mailer
        self._inbox_url = inbox_url

    def channel_for(self, event_type: str) -> str:
        """The channel chosen for a type; one that cannot be read counts as in_app."""
        try:
            return self._channels.channel_for(event_type)
        except Exception:
            logger.exception(
                "Could not read the channel setting for %s; using in_app", event_type
            )
            return "in_app"

    def send_email(self, *, channel: str, event_type: str, recipient_id: str) -> None:
        """Send the email half of a newly stored notification.

        Nothing here may break the caller: the notification is already stored,
        so a failure is logged and the notification stays as it was.
        """
        if channel not in ("email", "both"):
            return
        try:
            address = self._addresses.email_for(recipient_id)
            if address is None:
                logger.warning(
                    "Not emailing %s for recipient %s: no email address",
                    event_type,
                    recipient_id,
                )
                return
            self._mailer.send(
                to=address,
                subject=f"New notification: {event_type}",
                body=(
                    f"You have a new {event_type} notification.\n\n"
                    f"Open your inbox: {self._inbox_url}"
                ),
            )
        except Exception:
            logger.exception(
                "Could not email %s to recipient %s", event_type, recipient_id
            )
