from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError, AuthUnknownError

from app.integrations import get_supabase_client
from app.main import app


@pytest.fixture
def supabase() -> Iterator[Mock]:
    supabase = Mock()
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    yield supabase
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
