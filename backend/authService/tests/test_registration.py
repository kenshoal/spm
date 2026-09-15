from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.integrations import get_supabase_client
from app.main import app


def test_register_uses_supabase_auth() -> None:
    supabase = Mock()
    supabase.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-id", email="member@example.com"),
        session=None,
    )
    app.dependency_overrides[get_supabase_client] = lambda: supabase

    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": "member@example.com",
                    "password": "secure-password",
                },
            )
    finally:
        app.dependency_overrides.clear()

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
