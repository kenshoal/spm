import json

import httpx2
import pytest

from app.repository import NotificationStoreError, SupabaseNotificationRepository

NOTIFICATION_ID = "5b0c7a52-3a8e-4d0f-9f3e-2f6c1d9b8a10"


def stored_row(**overrides: object) -> dict[str, object]:
    return {
        "id": NOTIFICATION_ID,
        "recipient_id": "coord-1",
        "event_type": "coordinator_assigned",
        "payload": {"event_request_id": "11111111-1111-4111-8111-111111111111"},
        "event_id": None,
        "read_at": None,
        "created_at": "2026-09-29T10:00:00+00:00",
        **overrides,
    }


def repository_answering(handler) -> SupabaseNotificationRepository:
    return SupabaseNotificationRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx2.MockTransport(handler),
    )


# AC6-N1 (negative): A repeated event (same recipient and event_id) must be dropped by the
# database, not stored twice, so a retried hook never notifies someone twice.
def test_save_inserts_and_ignores_duplicates() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["on_conflict"] = request.url.params.get("on_conflict")
        captured["prefer"] = request.headers.get("prefer")
        captured["apikey"] = request.headers.get("apikey")
        captured["body"] = json.loads(request.content)
        return httpx2.Response(201, json=[stored_row(event_id="evt-1")])

    created = repository_answering(handler).save(
        event_type="coordinator_assigned",
        recipient_id="coord-1",
        payload={"event_request_id": "11111111-1111-4111-8111-111111111111"},
        event_id="evt-1",
    )

    assert created is True
    assert captured == {
        "method": "POST",
        "path": "/rest/v1/notifications",
        "on_conflict": "recipient_id,event_id",
        "prefer": "resolution=ignore-duplicates,return=representation",
        "apikey": "sb_secret_test",
        "body": {
            "event_type": "coordinator_assigned",
            "recipient_id": "coord-1",
            "payload": {"event_request_id": "11111111-1111-4111-8111-111111111111"},
            "event_id": "evt-1",
            "in_inbox": True,
        },
    }


# AC6-N1 (negative): PostgREST answers an ignored duplicate with an empty list; that must
# be reported as "not created" so the service can log it as a duplicate.
def test_save_reports_an_ignored_duplicate() -> None:
    repository = repository_answering(lambda request: httpx2.Response(201, json=[]))

    created = repository.save(
        event_type="coordinator_assigned",
        recipient_id="coord-1",
        payload={},
        event_id="evt-1",
    )

    assert created is False


# AC6-H1 (happy): The inbox shows only the caller's notifications, newest first.
def test_list_for_recipient_filters_and_orders() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.update(request.url.params)
        return httpx2.Response(200, json=[stored_row()])

    rows = repository_answering(handler).list_for_recipient(
        "coord-1", unread_only=False, limit=50
    )

    assert rows == [stored_row()]
    assert captured == {
        "recipient_id": "eq.coord-1",
        "in_inbox": "eq.true",
        "order": "created_at.desc,id.desc",
        "limit": "50",
        "select": "*",
    }


# AC6-P1 (partition): "Unread only" is filtered in the database, not after fetching.
def test_list_for_recipient_can_filter_to_unread() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.update(request.url.params)
        return httpx2.Response(200, json=[])

    repository_answering(handler).list_for_recipient(
        "coord-1", unread_only=True, limit=10
    )

    assert captured["read_at"] == "is.null"


# AC6-H2 (happy): Marking as read is scoped to the recipient, so nobody can mark (or
# discover) someone else's notification, and it keeps the first read time.
def test_mark_read_updates_only_the_recipients_unread_notification() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["method"] = request.method
        captured["params"] = dict(request.url.params)
        captured["body"] = json.loads(request.content)
        return httpx2.Response(
            200, json=[stored_row(read_at="2026-09-29T11:00:00+00:00")]
        )

    row = repository_answering(handler).mark_read(NOTIFICATION_ID, "coord-1")

    assert row is not None
    assert row["read_at"] == "2026-09-29T11:00:00+00:00"
    assert captured["method"] == "PATCH"
    assert captured["params"] == {
        "id": f"eq.{NOTIFICATION_ID}",
        "recipient_id": "eq.coord-1",
        "read_at": "is.null",
    }
    assert set(captured["body"]) == {"read_at"}


# AC6-P3 (partition): Marking an already-read notification again succeeds and returns it
# unchanged, so a double click in the inbox is not an error.
def test_mark_read_returns_an_already_read_notification() -> None:
    already_read = stored_row(read_at="2026-09-29T10:30:00+00:00")

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "PATCH":
            return httpx2.Response(200, json=[])
        return httpx2.Response(200, json=[already_read])

    row = repository_answering(handler).mark_read(NOTIFICATION_ID, "coord-1")

    assert row == already_read


# AC6-N5 (negative): Unknown ids and other people's notifications look the same: absent.
def test_mark_read_returns_none_when_not_the_recipients() -> None:
    repository = repository_answering(lambda request: httpx2.Response(200, json=[]))

    assert repository.mark_read(NOTIFICATION_ID, "someone-else") is None


# AC6-X4 (cross-cutting): Legacy service-role keys are JWTs and must also be sent as a bearer
# token; new sb_secret keys must not be.
@pytest.mark.parametrize(
    ("key", "expected_authorization"),
    [("sb_secret_test", None), ("eyJ.legacy.jwt", "Bearer eyJ.legacy.jwt")],
)
def test_sends_the_key_the_way_supabase_expects(
    key: str, expected_authorization: str | None
) -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["authorization"] = request.headers.get("authorization")
        return httpx2.Response(200, json=[])

    SupabaseNotificationRepository(
        "https://project.supabase.co", key, transport=httpx2.MockTransport(handler)
    ).list_for_recipient("coord-1", unread_only=False, limit=1)

    assert captured["authorization"] == expected_authorization


# AC6-N3 (negative): Any Supabase failure surfaces as one error type the API maps to 502.
@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx2.Response(500, json={"message": "boom"}),
        lambda request: (_ for _ in ()).throw(httpx2.ConnectError("down")),
    ],
)
def test_supabase_failures_raise_store_error(handler) -> None:
    with pytest.raises(NotificationStoreError):
        repository_answering(handler).list_for_recipient(
            "coord-1", unread_only=False, limit=1
        )


# AC2-P3 (partition): an email-only notification is stored hidden from the inbox, so it
# still guards against duplicates without appearing in the list.
def test_save_can_store_a_notification_hidden_from_the_inbox() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(201, json=[stored_row(event_id="evt-1")])

    repository_answering(handler).save(
        event_type="coordinator_assigned",
        recipient_id="coord-1",
        payload={},
        event_id="evt-1",
        in_inbox=False,
    )

    assert captured["body"]["in_inbox"] is False  # type: ignore[index]
