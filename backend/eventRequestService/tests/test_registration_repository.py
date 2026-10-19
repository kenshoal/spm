"""SCRUM-21: the Supabase registration repository over a mocked transport."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.repositories import SupabaseRepositoryError
from app.repositories.registration_repository import (
    EVENT_COLUMNS,
    RegistrationRpcError,
    SupabaseRegistrationRepository,
)

NOW = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)


def make_repository(handler) -> SupabaseRegistrationRepository:  # type: ignore[no-untyped-def]
    return SupabaseRegistrationRepository(
        "https://example.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(handler),
    )


# AC1-X1 (cross-cutting): the event query asks only for public-view columns
def test_event_query_selects_no_internal_columns() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    make_repository(handler).get_event("e1")

    assert seen[0].url.params["select"] == EVENT_COLUMNS
    for internal in ("organiser_id", "venue_requirements", "accessibility_needs",
                     "equipment_requirements", "registration_needs"):
        assert internal not in EVENT_COLUMNS


# AC5-H1 (happy): register calls the database function with the attendee, event and clock
def test_register_calls_the_database_function() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"id": "r1", "status": "Registered"})

    row = make_repository(handler).register("e1", "a1", NOW)

    assert row["id"] == "r1"
    assert seen[0].url.path == "/rest/v1/rpc/register_for_event"
    assert json.loads(seen[0].content) == {
        "p_event_request_id": "e1",
        "p_attendee_id": "a1",
        "p_now": NOW.isoformat(),
    }


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("P0002", "event not found"),
        ("P0004", "registration not open"),
        ("P0004", "already registered"),
        ("P0004", "event full"),
    ],
)
# AC4-N2 (negative): a database refusal carries its SQLSTATE and reason, not prose to parse
def test_register_refusal_carries_errcode_and_reason(code: str, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": code, "message": message})

    with pytest.raises(RegistrationRpcError) as caught:
        make_repository(handler).register("e1", "a1", NOW)

    assert caught.value.errcode == code
    assert caught.value.reason == message


# AC5-N3 (negative): a Supabase outage is a repository error, never a refusal
@pytest.mark.parametrize("status_code", [500, 503])
def test_register_server_error_is_a_repository_error(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "boom"})

    with pytest.raises(SupabaseRepositoryError) as caught:
        make_repository(handler).register("e1", "a1", NOW)

    assert not isinstance(caught.value, RegistrationRpcError)


# AC5-N3 (negative): a network failure is a repository error
def test_register_network_failure_is_a_repository_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(SupabaseRepositoryError):
        make_repository(handler).register("e1", "a1", NOW)


# AC5-H2 (happy): an attendee's registrations are filtered by attendee and newest first
def test_list_for_attendee_filters_and_orders() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    make_repository(handler).list_for_attendee("a1")

    assert seen[0].url.params["attendee_id"] == "eq.a1"
    assert seen[0].url.params["order"] == "created_at.desc"


# AC4-B2 (boundary): only Registered rows count, grouped per event
def test_count_active_counts_registered_rows_per_event() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[{"event_request_id": "e1"}, {"event_request_id": "e1"},
                  {"event_request_id": "e2"}],
        )

    counts = make_repository(handler).count_active_for_events(["e1", "e2", "e3"])

    assert counts == {"e1": 2, "e2": 1, "e3": 0}
    assert seen[0].url.params["status"] == "eq.Registered"


# AC4-B3 (boundary): an event with no registrations counts zero, and no ids means no call
def test_count_active_with_no_rows_is_zero() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[])

    repository = make_repository(handler)
    assert repository.count_active("e1") == 0
    assert repository.count_active_for_events([]) == {}
    assert calls == 1


# AC5-N4 (negative): the duplicate check filters by event, attendee and
# Registered status, and reads one row at most
def test_has_active_queries_event_and_attendee() -> None:
    seen: list[httpx.Request] = []
    payloads: list[list[dict[str, str]]] = [[{"id": "r1"}], []]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payloads.pop(0))

    repository = make_repository(handler)

    assert repository.has_active("e1", "a1") is True
    assert repository.has_active("e1", "a1") is False
    assert seen[0].url.params["event_request_id"] == "eq.e1"
    assert seen[0].url.params["attendee_id"] == "eq.a1"
    assert seen[0].url.params["status"] == "eq.Registered"
    assert seen[0].url.params["limit"] == "1"
