"""SCRUM-22: the Supabase repository's withdrawal calls over a mocked transport."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.repositories import SupabaseRepositoryError
from app.repositories.registration_repository import (
    REGISTRATION_COLUMNS,
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


# AC1-R1 (happy): withdraw calls the database function with the agreed payload
def test_withdraw_calls_the_database_function() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "r1", "status": "Withdrawn"})

    row = make_repository(handler).withdraw("r1", "a1", NOW)

    assert row["status"] == "Withdrawn"
    assert seen[0].url.path == "/rest/v1/rpc/withdraw_registration"
    assert json.loads(seen[0].content) == {
        "p_registration_id": "r1",
        "p_attendee_id": "a1",
        "p_now": NOW.isoformat(),
    }


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("P0002", "registration not found"),
        ("P0004", "already withdrawn"),
        ("P0004", "withdrawal not permitted"),
    ],
)
# AC2-N7 (negative): a refusal carries its SQLSTATE and reason, not prose to parse
def test_withdraw_refusal_carries_errcode_and_reason(code: str, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": code, "message": message})

    with pytest.raises(RegistrationRpcError) as caught:
        make_repository(handler).withdraw("r1", "a1", NOW)

    assert caught.value.errcode == code
    assert caught.value.reason == message


# AC2-N6 (negative): a Supabase outage is a repository error, never a refusal
@pytest.mark.parametrize("status_code", [500, 503])
def test_withdraw_server_error_is_a_repository_error(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "boom"})

    with pytest.raises(SupabaseRepositoryError) as caught:
        make_repository(handler).withdraw("r1", "a1", NOW)

    assert not isinstance(caught.value, RegistrationRpcError)


# AC2-N6 (negative): a network failure is a repository error
def test_withdraw_network_failure_is_a_repository_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(SupabaseRepositoryError) as caught:
        make_repository(handler).withdraw("r1", "a1", NOW)

    assert not isinstance(caught.value, RegistrationRpcError)


# AC2-N2 (negative): get_registration filters by id and returns None when absent
def test_get_registration_filters_by_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    assert make_repository(handler).get_registration("r1") is None
    assert seen[0].url.path == "/rest/v1/event_registrations"
    assert seen[0].url.params["id"] == "eq.r1"
    assert seen[0].url.params["select"] == REGISTRATION_COLUMNS


# AC4-H1 (happy): the attendee's list selects withdrawn_at
def test_list_for_attendee_selects_withdrawn_at() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    make_repository(handler).list_for_attendee("a1")

    assert "withdrawn_at" in seen[0].url.params["select"]
