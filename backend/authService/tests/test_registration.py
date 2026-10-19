from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError, AuthUnknownError

from app.integrations import get_supabase_client
from app.main import app, get_admin_client, get_optional_admin_client


@pytest.fixture
def supabase() -> Iterator[Mock]:
    supabase = Mock()
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    app.dependency_overrides[get_optional_admin_client] = lambda: None
    yield supabase
    app.dependency_overrides.clear()


@pytest.fixture
def admin() -> Iterator[Mock]:
    admin_client = Mock()
    app.dependency_overrides[get_admin_client] = lambda: admin_client
    yield admin_client
    app.dependency_overrides.clear()


def test_register_uses_supabase_auth(client: TestClient, supabase: Mock) -> None:
    supabase.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-id", email="member@example.com"),
        session=None,
    )
    response = client.post(
        "/auth/register",
        json={"email": "member@example.com", "password": "secure-password"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": "user-id",
        "email": "member@example.com",
        "email_confirmation_required": True,
    }
    supabase.auth.sign_up.assert_called_once_with(
        {
            "email": "member@example.com",
            "password": "secure-password",
        }
    )


def test_register_rejects_short_password(client: TestClient, supabase: Mock) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "member@example.com", "password": "short"},
    )

    assert response.status_code == 422
    supabase.auth.sign_up.assert_not_called()


def test_login_returns_supabase_tokens(client: TestClient, supabase: Mock) -> None:
    supabase.auth.sign_in_with_password.return_value = SimpleNamespace(
        session=SimpleNamespace(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            token_type="bearer",
        )
    )
    response = client.post(
        "/auth/login",
        json={"email": "member@example.com", "password": "secure-password"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "token_type": "bearer",
    }
    supabase.auth.sign_in_with_password.assert_called_once_with(
        {"email": "member@example.com", "password": "secure-password"}
    )


@pytest.mark.parametrize(
    ("provider_error", "expected_status", "expected_detail"),
    [
        (
            AuthApiError("bad password", 400, "invalid_credentials"),
            401,
            "Invalid email or password",
        ),
        (
            AuthApiError("not confirmed", 400, "email_not_confirmed"),
            403,
            "Email confirmation required",
        ),
        (
            AuthApiError("rate limited", 429, "over_request_rate_limit"),
            429,
            "Too many login attempts",
        ),
        (
            AuthApiError("internal error", 500, None),
            502,
            "Authentication provider unavailable",
        ),
    ],
)
def test_login_maps_provider_errors(
    client: TestClient,
    supabase: Mock,
    provider_error: AuthApiError,
    expected_status: int,
    expected_detail: str,
) -> None:
    supabase.auth.sign_in_with_password.side_effect = provider_error

    response = client.post(
        "/auth/login",
        json={"email": "member@example.com", "password": "wrong-password"},
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


def test_login_rejects_empty_password(client: TestClient, supabase: Mock) -> None:
    response = client.post(
        "/auth/login", json={"email": "member@example.com", "password": ""}
    )

    assert response.status_code == 422
    supabase.auth.sign_in_with_password.assert_not_called()


def test_login_requires_session(client: TestClient, supabase: Mock) -> None:
    supabase.auth.sign_in_with_password.return_value = SimpleNamespace(session=None)

    response = client.post(
        "/auth/login",
        json={"email": "member@example.com", "password": "secure-password"},
    )

    assert response.status_code == 502


def test_login_maps_network_failure_to_bad_gateway(
    client: TestClient, supabase: Mock
) -> None:
    supabase.auth.sign_in_with_password.side_effect = AuthUnknownError(
        "connection failed", ConnectionError()
    )

    response = client.post(
        "/auth/login",
        json={"email": "member@example.com", "password": "secure-password"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Authentication provider unavailable"}


def test_current_user_verifies_supabase_access_token(
    client: TestClient, supabase: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id",
            email="member@example.com",
            app_metadata={"role": "event_organiser"},
            user_metadata={"role": "admin"},
        )
    )

    response = client.get("/auth/me", headers={"Authorization": "Bearer access-token"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "id": "user-id",
        "email": "member@example.com",
        "role": "event_organiser",
        "roles": ["event_organiser"],
    }
    supabase.auth.get_user.assert_called_once_with("access-token")


def test_current_user_returns_all_roles(client: TestClient, supabase: Mock) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id",
            email="member@example.com",
            app_metadata={"roles": ["event_operations_manager", "technical_support"]},
        )
    )

    response = client.get("/auth/me", headers={"Authorization": "Bearer access-token"})

    assert response.status_code == 200
    assert response.json()["role"] == "event_operations_manager"
    assert response.json()["roles"] == [
        "event_operations_manager",
        "technical_support",
    ]


def test_current_user_reads_roles_from_staff_roles_table(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    app.dependency_overrides[get_optional_admin_client] = lambda: admin
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id",
            email="member@example.com",
            app_metadata={"role": "event_coordinator"},
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(
            data=[
                {"role": "event_operations_manager"},
                {"role": "technical_support"},
            ]
        )
    )

    response = client.get("/auth/me", headers={"Authorization": "Bearer access-token"})

    assert response.status_code == 200
    assert response.json()["roles"] == [
        "event_operations_manager",
        "technical_support",
    ]
    admin.table.assert_called_with("staff_roles")


@pytest.mark.parametrize("app_metadata", [{}, None])
def test_current_user_defaults_role_to_attendee(
    client: TestClient, supabase: Mock, app_metadata: dict | None
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id", email="member@example.com", app_metadata=app_metadata
        )
    )

    response = client.get("/auth/me", headers={"Authorization": "Bearer access-token"})

    assert response.status_code == 200
    assert response.json()["role"] == "attendee"
    assert response.json()["roles"] == ["attendee"]


def test_admin_assigns_role(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id",
            email="admin@example.com",
            app_metadata={"role": "admin"},
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "admin"}]),
        SimpleNamespace(data=[{"role": "technical_support"}]),
    ]
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id",
            email="member@example.com",
            app_metadata={"role": "technical_support"},
        )
    )

    response = client.patch(
        "/auth/users/user-id/role",
        headers={"Authorization": "Bearer admin-token"},
        json={"role": "technical_support"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-id",
        "email": "member@example.com",
        "role": "technical_support",
    }
    admin.table.return_value.upsert.assert_called_once_with(
        {
            "user_id": "user-id",
            "role": "technical_support",
            "assigned_by": "admin-id",
        }
    )
    admin.auth.admin.update_user_by_id.assert_called_once_with(
        "user-id",
        {"app_metadata": {"role": "technical_support", "roles": ["technical_support"]}},
    )


def test_operations_manager_assigns_event_coordinator(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="manager-id",
            email="manager@example.com",
            app_metadata={"roles": ["event_operations_manager"]},
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
        SimpleNamespace(data=[{"role": "event_coordinator"}]),
    ]
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id",
            email="member@example.com",
            app_metadata={"roles": ["event_coordinator"]},
        )
    )

    response = client.patch(
        "/auth/users/user-id/role",
        headers={"Authorization": "Bearer manager-token"},
        json={"role": "event_coordinator"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "event_coordinator"
    admin.table.return_value.upsert.assert_called_once_with(
        {
            "user_id": "user-id",
            "role": "event_coordinator",
            "assigned_by": "manager-id",
        }
    )
    admin.auth.admin.update_user_by_id.assert_called_once_with(
        "user-id",
        {
            "app_metadata": {
                "role": "event_coordinator",
                "roles": ["event_coordinator"],
            }
        },
    )


# Purpose: event_operations_manager is assignable after Coordinator assignment
# (eventRequestService) introduced the role — confirms it works
# through the real endpoint, not just directly via the Admin API.
def test_admin_assigns_event_operations_manager_role(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id",
            email="admin@example.com",
            app_metadata={"role": "admin"},
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "admin"}]),
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
    ]
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id",
            email="ops@example.com",
            app_metadata={"role": "event_operations_manager"},
        )
    )

    response = client.patch(
        "/auth/users/user-id/role",
        headers={"Authorization": "Bearer admin-token"},
        json={"role": "event_operations_manager"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "event_operations_manager"


# AC1-H1 (happy): an admin can grant the SCRUM-60 Safety Officer role.
def test_admin_assigns_safety_officer_role(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id",
            email="admin@example.com",
            app_metadata={"role": "admin"},
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "admin"}]),
        SimpleNamespace(data=[{"role": "safety_officer"}]),
    ]
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id",
            email="safety@example.com",
            app_metadata={"role": "safety_officer"},
        )
    )

    response = client.patch(
        "/auth/users/user-id/role",
        headers={"Authorization": "Bearer admin-token"},
        json={"role": "safety_officer"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "safety_officer"


@pytest.mark.parametrize(
    ("caller_role", "app_metadata"),
    [
        ("technical_support", {"role": "technical_support"}),
        ("event_operations_manager", {"role": "event_operations_manager"}),
        ("attendee", {}),
        ("attendee", None),
    ],
)
def test_admin_endpoint_requires_admin_role(
    client: TestClient, supabase: Mock, admin: Mock, caller_role: str, app_metadata
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id", email="member@example.com", app_metadata=app_metadata
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": caller_role}])
    )

    response = client.patch(
        "/auth/users/user-id/role",
        headers={"Authorization": "Bearer token"},
        json={"role": "technical_support"},
    )

    assert response.status_code == 403
    admin.table.return_value.upsert.assert_not_called()
    admin.auth.admin.update_user_by_id.assert_not_called()


def test_admin_endpoint_requires_authentication(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    response = client.patch(
        "/auth/users/user-id/role", json={"role": "technical_support"}
    )

    assert response.status_code == 401
    admin.auth.admin.update_user_by_id.assert_not_called()


def test_admin_endpoint_rejects_invalid_role(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id", email="admin@example.com", app_metadata={"role": "admin"}
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "admin"}])
    )

    response = client.patch(
        "/auth/users/user-id/role",
        headers={"Authorization": "Bearer admin-token"},
        json={"role": "superuser"},
    )

    assert response.status_code == 422
    admin.table.return_value.upsert.assert_not_called()
    admin.auth.admin.update_user_by_id.assert_not_called()


def test_admin_endpoint_maps_missing_user(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id", email="admin@example.com", app_metadata={"role": "admin"}
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "admin"}])
    )
    admin.auth.admin.get_user_by_id.side_effect = AuthApiError(
        "user not found", 404, "user_not_found"
    )

    response = client.patch(
        "/auth/users/missing-user/role",
        headers={"Authorization": "Bearer admin-token"},
        json={"role": "technical_support"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_admin_endpoint_maps_role_store_failure(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id", email="admin@example.com", app_metadata={"role": "admin"}
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "admin"}])
    )
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-id", email="member@example.com")
    )
    admin.table.return_value.upsert.return_value.execute.side_effect = APIError(
        {"message": "offline", "code": "PGRST000", "hint": None, "details": None}
    )

    response = client.patch(
        "/auth/users/user-id/role",
        headers={"Authorization": "Bearer admin-token"},
        json={"role": "technical_support"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Role store unavailable"}


def test_admin_endpoint_returns_503_without_secret_key(
    client: TestClient,
    supabase: Mock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id", email="admin@example.com", app_metadata={"role": "admin"}
        )
    )
    try:
        response = client.patch(
            "/auth/users/user-id/role",
            headers={"Authorization": "Bearer admin-token"},
            json={"role": "technical_support"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer ", "Bearer a b"])
def test_current_user_requires_bearer_token(
    client: TestClient, supabase: Mock, authorization: str | None
) -> None:
    response = client.get(
        "/auth/me",
        headers={"Authorization": authorization} if authorization is not None else {},
    )

    assert response.status_code == 401
    supabase.auth.get_user.assert_not_called()


def test_current_user_rejects_invalid_token(client: TestClient, supabase: Mock) -> None:
    supabase.auth.get_user.side_effect = AuthApiError("expired", 401, "bad_jwt")

    response = client.get("/auth/me", headers={"Authorization": "Bearer expired"})

    assert response.status_code == 401


def test_current_user_maps_provider_failure(client: TestClient, supabase: Mock) -> None:
    supabase.auth.get_user.side_effect = AuthUnknownError(
        "connection failed", ConnectionError()
    )

    response = client.get("/auth/me", headers={"Authorization": "Bearer token"})

    assert response.status_code == 502


def _caller(supabase: Mock, roles: list[str]) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="caller-id", email="caller@example.com", app_metadata={"roles": roles}
        )
    )


COORDINATOR_EMAILS = {"coord-a": "alex@example.com", "coord-b": "blair@example.com"}


# Purpose: SCRUM-14 — an Operations Manager can list coordinators to choose from.
def test_operations_manager_lists_event_coordinators(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
        SimpleNamespace(data=[{"user_id": "coord-b"}, {"user_id": "coord-a"}]),
    ]
    admin.auth.admin.get_user_by_id.side_effect = lambda user_id: SimpleNamespace(
        user=SimpleNamespace(id=user_id, email=COORDINATOR_EMAILS[user_id])
    )

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"id": "coord-a", "email": "alex@example.com"},
        {"id": "coord-b", "email": "blair@example.com"},
    ]
    admin.table.return_value.select.return_value.eq.assert_called_with(
        "role", "event_coordinator"
    )


# Purpose: An Operations Manager may list coordinators only, not other staff roles.
def test_operations_manager_cannot_list_other_roles(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "event_operations_manager"}])
    )

    response = client.get(
        "/auth/users?role=venue_staff",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 403


# Purpose: An admin may list the holders of any role.
def test_admin_lists_any_role(client: TestClient, supabase: Mock, admin: Mock) -> None:
    _caller(supabase, ["admin"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "admin"}]),
        SimpleNamespace(data=[{"user_id": "venue-1"}]),
    ]
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(id="venue-1", email="venue@example.com")
    )

    response = client.get(
        "/auth/users?role=venue_staff", headers={"Authorization": "Bearer admin-token"}
    )

    assert response.status_code == 200
    assert response.json() == [{"id": "venue-1", "email": "venue@example.com"}]


# Purpose: Roles without assignment duties cannot enumerate staff.
def test_organiser_cannot_list_users(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_organiser"])
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "event_organiser"}])
    )

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer organiser-token"},
    )

    assert response.status_code == 403


# Purpose: Listing staff requires a session.
def test_list_users_requires_authentication(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    response = client.get("/auth/users?role=event_coordinator")

    assert response.status_code == 401


# Purpose: A role row left behind by a deleted account does not break the picker.
def test_list_users_skips_deleted_accounts(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
        SimpleNamespace(data=[{"user_id": "gone"}, {"user_id": "coord-a"}]),
    ]

    def get_user(user_id: str) -> SimpleNamespace:
        if user_id == "gone":
            raise AuthApiError("user not found", 404, "user_not_found")
        return SimpleNamespace(user=SimpleNamespace(id=user_id, email="alex@example.com"))

    admin.auth.admin.get_user_by_id.side_effect = get_user

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 200
    assert response.json() == [{"id": "coord-a", "email": "alex@example.com"}]


# Purpose: A role-store outage is reported as a gateway failure, not an empty list.
def test_list_users_maps_role_store_failure(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
        APIError({"message": "offline", "code": "PGRST000", "hint": None, "details": None}),
    ]

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Role store unavailable"}
