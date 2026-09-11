from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from app.models import UserCreate, UserInDB
from app.security import hash_password


class DuplicateEmailError(Exception):
    """Raised when an email is already registered."""


class UserRepository(Protocol):
    def create(self, user: UserCreate) -> UserInDB: ...

    def get_by_email(self, email: str) -> UserInDB | None: ...


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users_by_email: dict[str, UserInDB] = {}
        self._lock = Lock()

    @staticmethod
    def _email_key(email: str) -> str:
        return email.casefold()

    def create(self, user: UserCreate) -> UserInDB:
        email_key = self._email_key(str(user.email))

        with self._lock:
            if email_key in self._users_by_email:
                raise DuplicateEmailError

            stored_user = UserInDB(
                id=uuid4(),
                email=user.email,
                display_name=user.display_name,
                created_at=datetime.now(UTC),
                password_hash=hash_password(user.password.get_secret_value()),
            )
            self._users_by_email[email_key] = stored_user

        return stored_user

    def get_by_email(self, email: str) -> UserInDB | None:
        return self._users_by_email.get(self._email_key(email))
