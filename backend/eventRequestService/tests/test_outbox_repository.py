import json

import httpx
import pytest

from app.repositories import SupabaseOutboxRepository, SupabaseRepositoryError


def outbox_row(**overrides: object) -> dict[str, object]:
    return {
        "id": "5b0b8d4e-2f53-4a5e-9a51-1c2f0f6c7a10",
        "event_request_id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
        "organiser_id": "9a1c3f52-7d4e-4b8a-8c11-2e5f6a7b8c9d",
        "event_type": "event_request.submitted",
        "payload": {
            "event_request_id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
            "organiser_id": "9a1c3f52-7d4e-4b8a-8c11-2e5f6a7b8c9d",
            "status": "Submitted",
        },
        "occurred_at": "2026-10-02T03:00:00+00:00",
        "published_at": None,
        **overrides,
    }


# AC1-H2 (happy): Only events not yet delivered are fetched, oldest first, so the relay
# never re-sends delivered events and works through a backlog in order.
def test_list_unpublished_requests_oldest_unpublished_rows() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[outbox_row()])

    repository = SupabaseOutboxRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    rows = repository.list_unpublished(limit=25)

    assert captured == {
        "method": "GET",
        "path": "/rest/v1/event_request_outbox",
        "params": {
            "published_at": "is.null",
            "order": "occurred_at.asc,id.asc",
            "limit": "25",
            "select": "*",
        },
    }
    assert rows == [outbox_row()]


# AC1-H2 (happy): Marking is scoped to one still-unpublished row, so a repeat never
# overwrites the first delivery time.
def test_mark_published_updates_only_that_unpublished_row() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        captured["body"] = json.loads(request.content)
        return httpx.Response(204)

    repository = SupabaseOutboxRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    repository.mark_published("5b0b8d4e-2f53-4a5e-9a51-1c2f0f6c7a10")

    assert captured["method"] == "PATCH"
    assert captured["path"] == "/rest/v1/event_request_outbox"
    assert captured["params"] == {
        "id": "eq.5b0b8d4e-2f53-4a5e-9a51-1c2f0f6c7a10",
        "published_at": "is.null",
    }
    assert set(captured["body"]) == {"published_at"}
    assert captured["body"]["published_at"]


# AC1-N1 (negative): Supabase failures surface as the service's own error type, which the
# relay loop catches, instead of leaking httpx exceptions.
@pytest.mark.parametrize("call", ["list_unpublished", "mark_published"])
def test_supabase_failure_raises_repository_error(call: str) -> None:
    repository = SupabaseOutboxRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )

    with pytest.raises(SupabaseRepositoryError):
        if call == "list_unpublished":
            repository.list_unpublished(limit=25)
        else:
            repository.mark_published("5b0b8d4e-2f53-4a5e-9a51-1c2f0f6c7a10")
