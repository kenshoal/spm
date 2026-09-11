"""Persistence boundaries for authService."""

from app.repositories.users import (
    DuplicateEmailError,
    InMemoryUserRepository,
    UserRepository,
)

__all__ = [
    "DuplicateEmailError",
    "InMemoryUserRepository",
    "UserRepository",
]
