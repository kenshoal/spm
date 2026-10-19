import json

import httpx
import pytest

from app.repositories import (
    EventRequestRpcError,
    SupabaseEventRequestRepository,
    SupabaseRepositoryError,
)


def response_row(**overrides: object) -> dict[str, object]:
    return {
        "id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
        "organiser_id": "organiser-1",
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


def change_response_row(**overrides: object) -> dict[str, object]:
    return {
        "id": "73fe8745-8147-48ee-b565-41e34811373c",
        "event_request_id": "0f73ff70-9ec6-4bc2-b3de-617760cfd507",
        "organiser_id": "843fb1b8-0e0b-4af3-a237-5fe862ce9e36",
        "status": "Pending",
        "explanation": "Increase attendance",
        "proposed_changes": {"expected_attendance": 80},
        "base_event_updated_at": "2026-10-04T01:00:00+00:00",
        "coordinator_id": None,
        "decision_reason": None,
        "created_at": "2026-10-04T02:00:00+00:00",
        "decided_at": None,
        **overrides,
    }


# AC1-H1 (happy): repository creation targets the atomic change-request function
def test_create_change_request_posts_expected_rpc_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=change_response_row())

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.create_change_request(
        "request-1", "organiser-1", "Increase attendance", {"expected_attendance": 80}
    )

    assert captured == {
        "path": "/rest/v1/rpc/create_event_change_request",
        "body": {
            "p_event_request_id": "request-1",
            "p_organiser_id": "organiser-1",
            "p_explanation": "Increase attendance",
            "p_proposed_changes": {"expected_attendance": 80},
        },
    }
    assert row["status"] == "Pending"


# AC3-H1 (happy): repository decisions target the exact event and amendment atomically
def test_decide_change_request_posts_expected_rpc_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=change_response_row(status="Approved"))

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler)
    )
    row = repository.decide_change_request(
        "request-1", "change-1", "coord-1", "Approved", None
    )

    assert captured == {
        "path": "/rest/v1/rpc/decide_event_change_request",
        "body": {
            "p_event_request_id": "request-1",
            "p_change_request_id": "change-1",
            "p_coordinator_id": "coord-1",
            "p_decision": "Approved",
            "p_reason": None,
        },
    }
    assert row["status"] == "Approved"


# Purpose: Verifies draft creation uses the server-only key and organiser identity.
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
            "organiser_id": "organiser-1",
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
            "organiser_id": "organiser-1",
            "status": "Draft",
            "event_name": "Community Dinner",
        },
    }
    assert created["status"] == "Draft"


# Purpose: Confirms retrieval filters by both request ID and organiser ID.
def test_get_scopes_query_to_organiser() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[response_row()])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.get_for_organiser("request-1", "organiser-1")

    assert captured_query["id"] == "eq.request-1"
    assert captured_query["organiser_id"] == "eq.organiser-1"
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
    repository.update_for_organiser(
        "request-1", "organiser-1", {"event_name": "Updated"}
    )

    assert captured["method"] == "PATCH"
    assert captured["query"] == {
        "id": "eq.request-1",
        "organiser_id": "eq.organiser-1",
        "status": "eq.Draft",
        "select": "*",
    }
    assert captured["body"] == {"event_name": "Updated"}


# Purpose: Makes submission a single owner-scoped Draft-to-Submitted database update.
def test_submit_atomically_scopes_and_changes_status() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["query"] = dict(request.url.params)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[response_row(status="Submitted")])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    submitted = repository.submit_for_organiser(
        "request-1", "organiser-1", {"event_name": "Complete request"}
    )

    assert captured["method"] == "PATCH"
    assert captured["query"] == {
        "id": "eq.request-1",
        "organiser_id": "eq.organiser-1",
        "status": "eq.Draft",
        "select": "*",
    }
    assert captured["body"] == {
        "event_name": "Complete request",
        "status": "Submitted",
    }
    assert submitted is not None
    assert submitted["status"] == "Submitted"


# Purpose: Confirms a status transition is scoped to the expected current status.
def test_update_status_scopes_query_to_from_status() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["query"] = dict(request.url.params)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[response_row(status="Under Review")])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.update_status("request-1", "Submitted", "Under Review")

    assert captured["method"] == "PATCH"
    assert captured["query"] == {
        "id": "eq.request-1",
        "status": "eq.Submitted",
        "select": "*",
    }
    assert captured["body"] == {"status": "Under Review"}
    assert row is not None
    assert row["status"] == "Under Review"


# Purpose: A row not currently in from_status means no rows match.
def test_update_status_returns_none_when_not_in_from_status() -> None:
    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
    )

    assert repository.update_status("request-1", "Submitted", "Under Review") is None


# Purpose: Prevents deletion unless ID, owner, and Draft status all match.
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
    deleted = repository.delete_for_organiser("request-1", "organiser-1")

    assert captured["method"] == "DELETE"
    assert captured["query"] == {
        "id": "eq.request-1",
        "organiser_id": "eq.organiser-1",
        "status": "eq.Draft",
        "select": "id",
    }
    assert deleted is True


# Purpose: The status lookup spans every organiser for the Operations Manager queue.
def test_list_by_status_queries_across_organisers() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    repository.list_by_status("Submitted")

    assert captured_query == {
        "status": "eq.Submitted",
        "order": "created_at.desc",
        "select": "*",
    }
    assert "organiser_id" not in captured_query


# Purpose: Confirms batch lookups query the exact ID list, newest first.
def test_get_by_ids_queries_id_list_ordered_newest_first() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[response_row()])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    repository.get_by_ids(["request-1", "request-2"])

    assert captured_query["id"] == "in.(request-1,request-2)"
    assert captured_query["order"] == "created_at.desc"


# Purpose: An empty ID list skips Supabase.
def test_get_by_ids_returns_empty_list_without_querying() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Supabase should not be called for an empty ID list")

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )

    assert repository.get_by_ids([]) == []


# Purpose: Converts upstream Supabase failures into the service's repository error.
def test_supabase_failure_raises_repository_error() -> None:
    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"message": "failure"})
        ),
    )

    with pytest.raises(SupabaseRepositoryError):
        repository.list_for_organiser("organiser-1")


# Purpose: Verifies the coordinator transition RPC call targets the database
# function with the caller's identity and asks PostgREST for a single object.
def test_advance_by_coordinator_posts_expected_rpc_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["accept"] = request.headers.get("accept")
        return httpx.Response(200, json=response_row(status="Under Review"))

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.advance_by_coordinator("request-1", "coord-1", "Under Review")

    assert captured["method"] == "/rest/v1/rpc/advance_event_request_by_coordinator"
    assert captured["body"] == {
        "p_event_request_id": "request-1",
        "p_coordinator_id": "coord-1",
        "p_to_status": "Under Review",
    }
    assert captured["accept"] == "application/vnd.pgrst.object+json"
    assert row["status"] == "Under Review"


# Purpose: Review outcomes and reasons are sent to the atomic decision RPC unchanged.
def test_decide_by_coordinator_posts_expected_rpc_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=response_row(status="Changes Requested"))

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.decide_by_coordinator(
        "request-1",
        "coord-1",
        "Changes Requested",
        "Clarify the equipment plan.",
    )

    assert captured["path"] == "/rest/v1/rpc/decide_event_request_by_coordinator"
    assert captured["body"] == {
        "p_event_request_id": "request-1",
        "p_coordinator_id": "coord-1",
        "p_decision_status": "Changes Requested",
        "p_reason": "Clarify the equipment plan.",
    }
    assert row["status"] == "Changes Requested"


# Purpose: Decision history uses a stable newest-first order even when timestamps tie.
def test_list_review_decisions_scopes_and_orders_query() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    repository.list_review_decisions("request-1")

    assert captured["path"] == "/rest/v1/event_request_review_decisions"
    assert captured["query"] == {
        "event_request_id": "eq.request-1",
        "order": "decided_at.desc,id.desc",
        "select": "*",
    }


# Purpose: Clarification responses use the owner-checking database RPC.
def test_respond_to_clarification_calls_atomic_rpc() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1})

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )
    row = repository.respond_to_clarification(
        "request-1", "organiser-1", "Microphone needed."
    )

    assert captured["path"] == "/rest/v1/rpc/respond_to_event_request_clarification"
    assert captured["body"] == {
        "p_event_request_id": "request-1",
        "p_organiser_id": "organiser-1",
        "p_response": "Microphone needed.",
    }
    assert row == {"id": 1}


@pytest.mark.parametrize(
    ("errcode",),
    [("P0002",), ("P0003",), ("P0004",)],
)
# Purpose: The RPC's Postgres errcodes surface on the raised error so services
# can map not-found, forbidden and not-allowed without parsing message text.
def test_rpc_rejection_carries_database_errcode(errcode: str) -> None:
    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400, json={"code": errcode, "message": "rejected"}
            )
        ),
    )

    with pytest.raises(EventRequestRpcError) as exc_info:
        repository.advance_by_coordinator("request-1", "coord-1", "Cancelled")

    assert exc_info.value.errcode == errcode


# Purpose: An RPC rejection with no parseable error body still raises the RPC
# error, with no errcode, rather than crashing on the malformed response.
def test_rpc_rejection_with_unreadable_body_has_no_errcode() -> None:
    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, text="gateway exploded")
        ),
    )

    with pytest.raises(EventRequestRpcError) as exc_info:
        repository.advance_by_coordinator("request-1", "coord-1", "Cancelled")

    assert exc_info.value.errcode is None


# Purpose: A transport-level failure on the RPC path stays a plain repository
# error — only database rejections are RPC errors.
def test_rpc_transport_failure_raises_repository_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SupabaseRepositoryError) as exc_info:
        repository.advance_by_coordinator("request-1", "coord-1", "Cancelled")

    assert not isinstance(exc_info.value, EventRequestRpcError)


def repository_capturing(
    captured: list[httpx.Request], rows: list[dict[str, object]]
) -> SupabaseEventRequestRepository:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=rows)

    return SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )


# AC2-H2 (happy): shared requests are read by organisation, excluding Drafts
def test_list_shared_with_organisation_excludes_drafts() -> None:
    captured: list[httpx.Request] = []
    row = response_row(status="Submitted", organisation_id="org-1")
    repository = repository_capturing(captured, [row])

    assert repository.list_shared_with_organisation("org-1") == [row]
    assert captured[0].url.path == "/rest/v1/event_requests"
    assert dict(captured[0].url.params) == {
        "organisation_id": "eq.org-1",
        "status": "neq.Draft",
        "order": "created_at.desc",
        "select": "*",
    }


# AC2-H1 (happy): an organiser's organisation is read from organisation_members
def test_get_organisation_id_reads_membership() -> None:
    captured: list[httpx.Request] = []
    repository = repository_capturing(captured, [{"organisation_id": "org-1"}])

    assert repository.get_organisation_id("user-1") == "org-1"
    assert captured[0].url.path == "/rest/v1/organisation_members"
    assert dict(captured[0].url.params) == {
        "user_id": "eq.user-1",
        "select": "organisation_id",
        "limit": "1",
    }


# AC3-P2 (partition): an organiser with no membership has no organisation
def test_get_organisation_id_returns_none_without_membership() -> None:
    repository = repository_capturing([], [])

    assert repository.get_organisation_id("user-1") is None


# AC4a-X2 (cross-cutting, SCRUM-60): the decision, reason and targets reach the
# database function unchanged.
def test_decide_safety_review_posts_expected_rpc_request() -> None:
    captured: list[httpx.Request] = []
    repository = repository_capturing(captured, response_row(status="Planning"))
    targets = [{"arrangement": "venue_booking", "id": "booking-1"}]

    row = repository.decide_safety_review(
        "request-1", "officer-1", "changes_requested", "Exit routes missing.", targets
    )

    assert captured[0].url.path == "/rest/v1/rpc/decide_safety_review"
    assert json.loads(captured[0].content) == {
        "p_event_request_id": "request-1",
        "p_officer_id": "officer-1",
        "p_decision": "changes_requested",
        "p_reason": "Exit routes missing.",
        "p_targets": targets,
    }
    assert row["status"] == "Planning"


# AC4a-X3 (cross-cutting, SCRUM-60): one event's safety reviews, newest first.
def test_list_safety_reviews_scopes_and_orders_query() -> None:
    captured: list[httpx.Request] = []
    repository = repository_capturing(captured, [])

    assert repository.list_safety_reviews("request-1") == []
    assert captured[0].url.path == "/rest/v1/safety_reviews"
    assert dict(captured[0].url.params) == {
        "event_request_id": "eq.request-1",
        "order": "decided_at.desc,id.desc",
        "select": "*",
    }


# AC4b-X1 (cross-cutting, SCRUM-60): the notice goes to the latest assignment's
# coordinator, not the first one.
def test_latest_coordinator_id_reads_newest_assignment() -> None:
    captured: list[httpx.Request] = []
    repository = repository_capturing(captured, [{"coordinator_id": "coord-2"}])

    assert repository.latest_coordinator_id("request-1") == "coord-2"
    assert captured[0].url.path == "/rest/v1/event_coordinator_assignments"
    assert dict(captured[0].url.params) == {
        "event_request_id": "eq.request-1",
        "order": "id.desc",
        "limit": "1",
        "select": "coordinator_id",
    }

