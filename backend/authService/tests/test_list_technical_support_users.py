"""SCRUM-19 G1: an Event Coordinator may list Technical Support Staff.

The coordination page's technical-support panel labels assigned staff with
emails from `GET /auth/users?role=technical_support` (AC4-X1). Only `admin`
could list that role before, so a coordinator received 403 and the panel fell
back to unusable UUID labels. These tests pin the widening: the coordinator may
list `technical_support` only, and no other caller or role gains access.
"""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.integrations import get_supabase_client, get_supabase_verifier_client
from app.main import app, get_admin_client


@pytest.fixture
def supabase() -> Iterator[Mock]:
    supabase = Mock()
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    app.dependency_overrides[get_supabase_verifier_client] = lambda: supabase
    yield supabase
    app.dependency_overrides.clear()


@pytest.fixture
def admin() -> Iterator[Mock]:
    admin_client = Mock()
    app.dependency_overrides[get_admin_client] = lambda: admin_client
    yield admin_client
    app.dependency_overrides.clear()


def _caller(supabase: Mock, roles: list[str]) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="caller-id", email="caller@example.com", app_metadata={"roles": roles}
        )
    )


STAFF_EMAILS = {"tss-b": "blair@example.com", "tss-a": "alex@example.com"}


# AC4-X1 (cross-cutting): the assigned Coordinator can list Technical Support
# Staff by email so the panel shows names, not raw ids (increment-2 plan G1).
def test_coordinator_lists_technical_support(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_coordinator"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_coordinator"}]),
        SimpleNamespace(data=[{"user_id": "tss-b"}, {"user_id": "tss-a"}]),
    ]
    admin.auth.admin.get_user_by_id.side_effect = lambda user_id: SimpleNamespace(
        user=SimpleNamespace(id=user_id, email=STAFF_EMAILS[user_id])
    )

    response = client.get(
        "/auth/users?role=technical_support",
        headers={"Authorization": "Bearer coordinator-token"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"id": "tss-a", "email": "alex@example.com"},
        {"id": "tss-b", "email": "blair@example.com"},
    ]
    admin.table.return_value.select.return_value.eq.assert_called_with(
        "role", "technical_support"
    )


# AC4-X1 (cross-cutting): the widening covers technical_support only — a
# coordinator listing any other role is refused before any role row is read.
@pytest.mark.parametrize(
    "role",
    [
        "admin",
        "attendee",
        "event_coordinator",
        "event_operations_manager",
        "event_organiser",
        "safety_officer",
        "venue_staff",
    ],
    ids=[
        "AC4-X1a",
        "AC4-X1b",
        "AC4-X1c",
        "AC4-X1d",
        "AC4-X1e",
        "AC4-X1f",
        "AC4-X1g",
    ],
)
def test_coordinator_cannot_list_other_roles(
    client: TestClient, supabase: Mock, admin: Mock, role: str
) -> None:
    _caller(supabase, ["event_coordinator"])
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "event_coordinator"}])
    )

    response = client.get(
        f"/auth/users?role={role}",
        headers={"Authorization": "Bearer coordinator-token"},
    )

    assert response.status_code == 403
    # Exactly one staff_roles read happened: the caller's own roles. The
    # requested directory was never queried, so nothing leaked.
    assert (
        admin.table.return_value.select.return_value.eq.return_value.execute.call_count
        == 1
    )


# AC4-X1 (cross-cutting): no other caller gains the directory — listing
# Technical Support Staff still requires a listing duty.
@pytest.mark.parametrize(
    "caller_roles",
    [
        ["technical_support"],
        ["event_organiser"],
        ["venue_staff"],
        ["safety_officer"],
        ["attendee"],
    ],
    ids=["AC4-X1h", "AC4-X1i", "AC4-X1j", "AC4-X1k", "AC4-X1l"],
)
def test_other_roles_cannot_list_technical_support(
    client: TestClient, supabase: Mock, admin: Mock, caller_roles: list[str]
) -> None:
    _caller(supabase, caller_roles)
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": caller_roles[0]}])
    )

    response = client.get(
        "/auth/users?role=technical_support",
        headers={"Authorization": "Bearer other-token"},
    )

    assert response.status_code == 403
    assert (
        admin.table.return_value.select.return_value.eq.return_value.execute.call_count
        == 1
    )


# AC4-X1 (cross-cutting): regression — an Operations Manager may still list
# coordinators only, so technical_support stays refused for them.
def test_operations_manager_cannot_list_technical_support(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "event_operations_manager"}])
    )

    response = client.get(
        "/auth/users?role=technical_support",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 403
    assert (
        admin.table.return_value.select.return_value.eq.return_value.execute.call_count
        == 1
    )
