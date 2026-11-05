"""SCRUM-24: the waiting-list outbox relay and its client notices (AC5).

The relay delivers the notices the database functions wrote inside their
transactions, after the fact. A notice is marked published only once
notificationService has accepted it (202), so an outage retries and nothing is
lost; the unique idempotency key means a retry is stored once (AC5-N1).
"""

import httpx
from registration_support import NOW
from waitlist_support import FakeWaitlistRepository

from app.services.notification_client import NotificationClient

ENTRY = "11111111-1111-4111-8111-111111111111"
ATTENDEE = "22222222-2222-4222-8222-222222222222"
KEY = "waitlist-offered:11111111-1111-4111-8111-111111111111:1893456000"

NOTICE_TYPES = [
    "waitlist_offered",
    "waitlist_offer_expiring",
    "waitlist_offer_expired",
    "waitlist_offer_revoked",
    "waitlist_closed",
    "waitlist_event_cancelled",
]


def outbox_row(event_type: str) -> dict:
    return {
        "id": ENTRY,
        "entry_id": ENTRY,
        "recipient_id": ATTENDEE,
        "event_type": event_type,
        "idempotency_key": KEY,
        "payload": {"event_request_id": "event-1", "event_name": "Community Dinner"},
        "occurred_at": NOW,
        "published_at": None,
    }


# AC5-H4 (happy): the client posts the agreed shape for every waiting-list type
def test_the_client_posts_the_agreed_shape_for_every_type() -> None:
    sent: list[dict] = []

    def handler(body: dict) -> httpx.Response:
        sent.append(body)
        return httpx.Response(202)

    client = NotificationClient("http://notifications.test/events")
    import app.services.notification_client as module

    original_post = module.httpx.post
    module.httpx.post = lambda url, **kwargs: handler(kwargs["json"])
    try:
        for event_type in NOTICE_TYPES:
            accepted = client.notify_waitlist_notice(
                event_type=event_type,
                recipient_id=ATTENDEE,
                idempotency_key=KEY,
                payload={"event_request_id": "event-1"},
            )
            assert accepted is True
    finally:
        module.httpx.post = original_post

    assert [body["event_type"] for body in sent] == NOTICE_TYPES
    for body in sent:
        assert body["recipient_id"] == ATTENDEE
        assert body["payload"] == {"event_request_id": "event-1"}


# AC5-H4 (happy): the key becomes the receiver's deduplicating event id
def test_the_client_derives_the_event_id_from_the_idempotency_key() -> None:
    from uuid import NAMESPACE_URL, uuid5

    captured: dict = {}

    def handler(body: dict) -> httpx.Response:
        captured.update(body)
        return httpx.Response(202)

    client = NotificationClient("http://notifications.test/events")
    import app.services.notification_client as module

    original_post = module.httpx.post
    module.httpx.post = lambda url, **kwargs: handler(kwargs["json"])
    try:
        client.notify_waitlist_notice(
            event_type="waitlist_offered",
            recipient_id=ATTENDEE,
            idempotency_key=KEY,
            payload={},
        )
    finally:
        module.httpx.post = original_post

    assert captured["event_id"] == str(uuid5(NAMESPACE_URL, KEY))


# AC5-N3 (negative, service side): an unreachable notification service leaves
# the notice pending and the pass retries it; nothing is undone
def test_a_failed_delivery_stays_pending_and_is_retried() -> None:
    calls: list[int] = []

    class FlakyClient:
        def notify_waitlist_notice(self, **kwargs: object) -> bool:
            calls.append(1)
            return len(calls) > 1  # the first attempt fails, the retry works

    from app.services.waitlist_notification_relay import WaitlistNotificationRelay

    repo = FakeWaitlistRepository()
    repo.outbox = [outbox_row("waitlist_offered")]
    relay = WaitlistNotificationRelay(repo, FlakyClient())

    assert relay.run_once() == 0
    assert repo.pending_outbox() != []

    assert relay.run_once() == 1
    assert repo.pending_outbox() == []
    assert repo.outbox[0]["published_at"] is not None


# AC5-H1 (happy, service side): a delivered notice posts exactly its stored key
def test_the_relay_posts_the_stored_key_and_type() -> None:
    seen: list[dict] = []

    class RecordingClient:
        def notify_waitlist_notice(self, **kwargs: object) -> bool:
            seen.append(dict(kwargs))
            return True

    from app.services.waitlist_notification_relay import WaitlistNotificationRelay

    repo = FakeWaitlistRepository()
    repo.outbox = [outbox_row("waitlist_offer_expired")]
    relay = WaitlistNotificationRelay(repo, RecordingClient())

    assert relay.run_once() == 1
    assert seen == [
        {
            "event_type": "waitlist_offer_expired",
            "recipient_id": ATTENDEE,
            "idempotency_key": KEY,
            "payload": {
                "event_request_id": "event-1",
                "event_name": "Community Dinner",
            },
        }
    ]
