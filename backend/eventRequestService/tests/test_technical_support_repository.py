"""SCRUM-19: the Supabase transport for technical support writes and reads.

Case IDs refer to docs/testcases/scrum_19_testcases.md (R layer). The
payloads and query shapes must match what migration 0051's functions and
tables accept.
"""

import json

import httpx
import pytest

from app.repositories import SupabaseRepositoryError
from app.repositories.technical_support_repository import (
    SupabaseTechnicalSupportRepository,
    TechnicalSupportRpcError,
)

EVENT = "11111111-1111-4111-8111-111111111111"
REQ_AV = "aaaa0000-0000-4000-8000-000000000001"


def requirement_row(**overrides: object) -> dict[str, object]:
    return {
        "id": REQ_AV,
        "event_request_id": EVENT,
        "description": "Two wireless mics",
        "skill_tag": "audio_visual",
        "recorded_by": "coord-1",
        "recorded_at": "2030-03-01T09:00:00+00:00",
        **overrides,
    }


def assignment_row(**overrides: object) -> dict[str, object]:
    return {
        "id": "bbbb0000-0000-4000-8000-000000000001",
        "requirement_id": REQ_AV,
        "event_request_id": EVENT,
        "staff_id": "tss-av",
        "assigned_by": "coord-1",
        "assigned_at": "2030-03-01T09:30:00+00:00",
        **overrides,
    }


def repository(handler: httpx.MockTransport) -> SupabaseTechnicalSupportRepository:
    return SupabaseTechnicalSupportRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )


# AC1-H1 (D payload shape): recording goes through the row-locking RPC
def test_record_requirement_sends_expected_rpc() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=requirement_row())

    created = repository(handler).record_requirement(
        {
            "event_request_id": EVENT,
            "coordinator_id": "coord-1",
            "description": "Two wireless mics",
            "skill_tag": "audio_visual",
        }
    )

    assert captured == {
        "method": "POST",
        "path": "/rest/v1/rpc/record_technical_support_requirement",
        "body": {
            "p_event_request_id": EVENT,
            "p_coordinator_id": "coord-1",
            "p_description": "Two wireless mics",
            "p_skill_tag": "audio_visual",
        },
    }
    assert created["skill_tag"] == "audio_visual"


# AC2-H1 (D payload shape): assigning goes through the row-locking RPC
def test_assign_sends_expected_rpc() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=assignment_row())

    assigned = repository(handler).assign(
        {
            "event_request_id": EVENT,
            "requirement_id": REQ_AV,
            "staff_id": "tss-av",
            "coordinator_id": "coord-1",
        }
    )

    assert captured == {
        "method": "POST",
        "path": "/rest/v1/rpc/assign_technical_support_staff",
        "body": {
            "p_event_request_id": EVENT,
            "p_requirement_id": REQ_AV,
            "p_staff_id": "tss-av",
            "p_coordinator_id": "coord-1",
        },
    }
    assert assigned["staff_id"] == "tss-av"


@pytest.mark.parametrize("errcode", ["P0002", "P0003", "P0004", "P0005", "23505"])
# AC2-N1, AC2-N3, AC3-P2 (error mapping input): a refusal keeps its errcode and
# the function's message so the service can map it without parsing prose
def test_rpc_refusal_preserves_errcode_and_reason(errcode: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"code": errcode, "message": "technical support requirement not found"},
        )

    with pytest.raises(TechnicalSupportRpcError) as exc_info:
        repository(handler).assign(
            {
                "event_request_id": EVENT,
                "requirement_id": REQ_AV,
                "staff_id": "tss-av",
                "coordinator_id": "coord-1",
            }
        )

    assert exc_info.value.errcode == errcode
    assert exc_info.value.reason == "technical support requirement not found"


@pytest.mark.parametrize("method", ["record_requirement", "assign"])
# AC2-N7 (R half): a transport or 5xx failure is the shared repository error,
# not an rpc refusal — the service must not notify on it
def test_transport_failure_raises_repository_error(method: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    repo = repository(handler)
    write = repo.record_requirement if method == "record_requirement" else repo.assign
    values = (
        {
            "event_request_id": EVENT,
            "coordinator_id": "coord-1",
            "description": "Two wireless mics",
            "skill_tag": "audio_visual",
        }
        if method == "record_requirement"
        else {
            "event_request_id": EVENT,
            "requirement_id": REQ_AV,
            "staff_id": "tss-av",
            "coordinator_id": "coord-1",
        }
    )

    with pytest.raises(SupabaseRepositoryError):
        write(values)


# AC4-B1 (R half): requirements are ordered by recorded_at then id
def test_list_requirements_orders_by_recorded_at_and_id() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[requirement_row()])

    rows = repository(handler).list_requirements(EVENT)

    assert captured_query["event_request_id"] == f"eq.{EVENT}"
    assert captured_query["order"] == "recorded_at.asc,id.asc"
    assert rows[0]["id"] == REQ_AV


# AC4-B1 (R half): assignments are ordered by assigned_at then id
def test_list_assignments_orders_by_assigned_at_and_id() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[assignment_row()])

    rows = repository(handler).list_assignments(EVENT)

    assert captured_query["event_request_id"] == f"eq.{EVENT}"
    assert captured_query["order"] == "assigned_at.asc,id.asc"
    assert rows[0]["staff_id"] == "tss-av"


# AC3-H1 (R half): one requirement is fetched by exact id
def test_get_requirement_fetches_by_id() -> None:
    captured_query: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_query.update(dict(request.url.params))
        return httpx.Response(200, json=[requirement_row()])

    row = repository(handler).get_requirement(REQ_AV)

    assert captured_query["id"] == f"eq.{REQ_AV}"
    assert captured_query["limit"] == "1"
    assert row is not None and row["id"] == REQ_AV


# AC2-N2 (R half): a missing requirement is None, not an error
def test_get_requirement_returns_none_when_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    assert repository(handler).get_requirement(REQ_AV) is None


# AC3-H1 (R half): candidates come from the suitability helper's RPC
def test_list_candidates_sends_expected_rpc() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=[
                {"staff_id": "tss-av", "already_assigned": True},
                {"staff_id": "tss-av2", "already_assigned": False},
            ],
        )

    candidates = repository(handler).list_candidates(REQ_AV)

    assert captured == {
        "path": "/rest/v1/rpc/list_technical_support_candidates",
        "body": {"p_requirement_id": REQ_AV},
    }
    assert candidates == [
        {"staff_id": "tss-av", "already_assigned": True},
        {"staff_id": "tss-av2", "already_assigned": False},
    ]


# AC2-N7 (R half): a read that cannot reach Supabase is the shared error
def test_read_failure_raises_repository_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(SupabaseRepositoryError):
        repository(handler).list_requirements(EVENT)
