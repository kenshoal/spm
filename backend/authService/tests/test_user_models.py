from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import UserCreate, UserInDB, UserPublic


def test_user_create_accepts_valid_input() -> None:
    user = UserCreate(
        email="member@example.com",
        display_name="Example Member",
        password="secure-password",
    )

    assert user.email == "member@example.com"
    assert user.password.get_secret_value() == "secure-password"
    assert "secure-password" not in repr(user)


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_user_create_rejects_invalid_password_length(password: str) -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="member@example.com",
            display_name="Example Member",
            password=password,
        )


def test_user_create_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="not-an-email",
            display_name="Example Member",
            password="secure-password",
        )


def test_public_user_does_not_contain_password_data() -> None:
    user = UserPublic(
        id=uuid4(),
        email="member@example.com",
        display_name="Example Member",
        created_at=datetime.now(UTC),
    )

    assert "password" not in user.model_dump()
    assert user.is_active is True


def test_database_user_keeps_only_the_password_hash() -> None:
    user = UserInDB(
        id=uuid4(),
        email="member@example.com",
        display_name="Example Member",
        created_at=datetime.now(UTC),
        password_hash="$argon2id$example",
    )

    assert user.password_hash == "$argon2id$example"
    assert "password" not in user.model_dump()
