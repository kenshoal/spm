import json

import httpx
import pytest

from app.repositories import SupabaseEventRequestRepository, SupabaseRepositoryError


def response_row(**overrides: object) -> dict[str, object]:
    return {
        "id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
        "organiser_id": None,
        "temporary_organiser_id": "organiser-1",
        "status": "Draft",
        "event_name": "Community Dinner",
        "purpose": None,
        "description": None,
        "proposed_date_times": [],
        "expected_attendance": None,
        "venue_requirements": None,
        "accessibility_needs": None,
        "equipment_requirements": None,
        "registration_needs": None,
        "created_at": "2026-09-15T12:00:00+00:00",
        "updated_at": "2026-09-15T12:00:00+00:00",
        **overrides,
    }


# Purpose: Verifies draft creation uses the server-only key and temporary identity columns.
def test_create_sends_expected_supabase_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["apikey"] = request.headers.get("apikey")
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[response_row()])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    created = repository.create(
        {
            "organiser_id": None,
            "temporary_organiser_id": "organiser-1",
            "status": "Draft",
            "event_name": "Community Dinner",
        }
    )

    assert captured == {
        "method": "POST",
        "path": "/rest/v1/event_requests",
        "apikey": "sb_secret_test",
        "authorization": None,
        "body": {
            "organiser_id": None,
            "temporary_organiser_id": "organiser-1",
            "status": "Draft",
            "event_name": "Community Dinner",
        },
    }
    assert created["status"] == "Draft"


# Purpose: Confirms retrieval filters by both request ID and temporary organiser ID.
def test_get_scopes_query_to_temporary_organiser() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[response_row()])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.get_for_temporary_organiser("request-1", "organiser-1")

    assert captured_query["id"] == "eq.request-1"
    assert captured_query["temporary_organiser_id"] == "eq.organiser-1"
    assert row is not None


# Purpose: Prevents a draft update from escaping the owner and Draft-status filters.
def test_update_scopes_query_to_owner_and_draft_status() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["query"] = dict(request.url.params)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[response_row(event_name="Updated")])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    repository.update_for_temporary_organiser(
        "request-1", "organiser-1", {"event_name": "Updated"}
    )

    assert captured["method"] == "PATCH"
    assert captured["query"] == {
        "id": "eq.request-1",
        "temporary_organiser_id": "eq.organiser-1",
        "status": "eq.Draft",
        "select": "*",
    }
    assert captured["body"] == {"event_name": "Updated"}


# Purpose: Prevents deletion of a request unless its ID, owner, and Draft status all match.
def test_delete_scopes_query_to_owner_and_draft_status() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=[response_row()])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    deleted = repository.delete_for_temporary_organiser(
        "request-1", "organiser-1"
    )

    assert captured["method"] == "DELETE"
    assert captured["query"] == {
        "id": "eq.request-1",
        "temporary_organiser_id": "eq.organiser-1",
        "status": "eq.Draft",
        "select": "id",
    }
    assert deleted is True


# Purpose: Converts upstream Supabase failures into the service's stable repository error.
def test_supabase_failure_raises_repository_error() -> None:
    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"message": "failure"})
        ),
    )

    with pytest.raises(SupabaseRepositoryError):
        repository.list_for_temporary_organiser("organiser-1")
