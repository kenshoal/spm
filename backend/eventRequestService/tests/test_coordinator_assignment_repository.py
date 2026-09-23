import json

import httpx
import pytest

from app.repositories import (
    SupabaseCoordinatorAssignmentRepository,
    SupabaseRepositoryError,
)


def response_row(**overrides: object) -> dict[str, object]:
    return {
        "id": 1,
        "event_request_id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
        "coordinator_id": "coord-1",
        "assigned_by": "ops-1",
        "assigned_at": "2026-09-15T12:00:00+00:00",
        **overrides,
    }


# Purpose: Verifies assignment creation posts to the coordinator-assignments table.
def test_create_sends_expected_supabase_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["apikey"] = request.headers.get("apikey")
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[response_row()])

    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    created = repository.create(
        {
            "event_request_id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
            "coordinator_id": "coord-1",
            "assigned_by": "ops-1",
        }
    )

    assert captured == {
        "method": "POST",
        "path": "/rest/v1/event_coordinator_assignments",
        "apikey": "sb_secret_test",
        "body": {
            "event_request_id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
            "coordinator_id": "coord-1",
            "assigned_by": "ops-1",
        },
    }
    assert created["coordinator_id"] == "coord-1"


# Purpose: Confirms "current assignment" is the most recent row by id.
def test_latest_orders_by_id_descending() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[response_row(id=2, coordinator_id="coord-2")])

    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.latest_for_event_request("0f73ff70-9ec6-4bc2-b3de-617760cfd507")

    assert captured_query["event_request_id"] == "eq.0f73ff70-9ec6-4bc2-b3de-617760cfd507"
    assert captured_query["order"] == "id.desc"
    assert captured_query["limit"] == "1"
    assert row is not None
    assert row["coordinator_id"] == "coord-2"


# Purpose: Confirms no rows means no assignment yet, not an error.
def test_latest_returns_none_when_never_assigned() -> None:
    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
    )

    assert repository.latest_for_event_request("missing") is None


# Purpose: Confirms awaiting-assignment reduces assigned rows to request ids.
def test_assigned_event_request_ids_filters_to_the_given_requests() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[{"event_request_id": "request-1"}])

    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    assigned = repository.assigned_event_request_ids(["request-1", "request-2"])

    assert captured_query["event_request_id"] == "in.(request-1,request-2)"
    assert captured_query["select"] == "event_request_id"
    assert assigned == {"request-1"}


# Purpose: Empty awaiting-assignment candidate lists skip Supabase.
def test_assigned_event_request_ids_skips_supabase_when_given_no_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Supabase should not be called for an empty id list")

    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )

    assert repository.assigned_event_request_ids([]) == set()


# Purpose: Confirms the coordinator queue query filters by coordinator_id.
def test_list_for_coordinator_filters_by_coordinator() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[response_row()])

    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    rows = repository.list_for_coordinator("coord-1")

    assert captured_query["coordinator_id"] == "eq.coord-1"
    assert len(rows) == 1


# Purpose: Confirms the candidate-assignments query targets the exact request IDs.
def test_list_for_event_requests_queries_id_list() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[response_row()])

    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    repository.list_for_event_requests(["request-1", "request-2"])

    assert captured_query["event_request_id"] == "in.(request-1,request-2)"


# Purpose: An empty request ID list skips Supabase.
def test_list_for_event_requests_returns_empty_list_without_querying() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Supabase should not be called for an empty ID list")

    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )

    assert repository.list_for_event_requests([]) == []


# Purpose: Converts upstream Supabase failures into the shared repository error.
def test_supabase_failure_raises_repository_error() -> None:
    repository = SupabaseCoordinatorAssignmentRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"message": "failure"})
        ),
    )

    with pytest.raises(SupabaseRepositoryError):
        repository.latest_for_event_request("0f73ff70-9ec6-4bc2-b3de-617760cfd507")
