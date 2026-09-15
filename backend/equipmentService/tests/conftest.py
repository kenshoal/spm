from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import get_client
from app.main import app


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeSupabase:
    def __init__(self) -> None:
        self.table_data: dict[str, Any] = {}
        self.inserts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.filters: list[tuple[str, Any]] = []

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, self.table_data.get(name))


class FakeQuery:
    def __init__(self, fake: FakeSupabase, data: Any) -> None:
        self._fake = fake
        self._data = data

    def select(self, *columns: str) -> "FakeQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self._fake.inserts.append(payload)
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self._fake.updates.append(payload)
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._fake.filters.append((column, value))
        return self

    def limit(self, count: int) -> "FakeQuery":
        return self

    def single(self) -> "FakeQuery":
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self._data)


@pytest.fixture
def fake_client() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def client(fake_client: FakeSupabase) -> TestClient:
    app.dependency_overrides[get_client] = lambda: fake_client
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
