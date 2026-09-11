from uuid import UUID

from fastapi.testclient import TestClient

from app.repositories import InMemoryUserRepository
from app.security import verify_password


def test_register_user_stores_a_hash_and_returns_public_data(
    client: TestClient,
    user_repository: InMemoryUserRepository,
) -> None:
    response = client.post(
        "/users",
        json={
            "email": "member@example.com",
            "display_name": "Example Member",
            "password": "secure-password",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["email"] == "member@example.com"
    assert body["display_name"] == "Example Member"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body

    stored_user = user_repository.get_by_email("member@example.com")
    assert stored_user is not None
    assert stored_user.password_hash != "secure-password"
    assert verify_password("secure-password", stored_user.password_hash)


def test_register_user_rejects_a_duplicate_email(
    client: TestClient,
) -> None:
    payload = {
        "email": "member@example.com",
        "display_name": "Example Member",
        "password": "secure-password",
    }

    assert client.post("/users", json=payload).status_code == 201
    response = client.post(
        "/users",
        json={**payload, "email": "MEMBER@example.com"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "An account with this email already exists"}


def test_register_user_validates_the_request(client: TestClient) -> None:
    response = client.post(
        "/users",
        json={
            "email": "not-an-email",
            "display_name": "Example Member",
            "password": "short",
        },
    )

    assert response.status_code == 422
