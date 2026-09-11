from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_user_repository
from app.main import app
from app.repositories import InMemoryUserRepository


@pytest.fixture
def user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def client(user_repository: InMemoryUserRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_user_repository] = lambda: user_repository

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
