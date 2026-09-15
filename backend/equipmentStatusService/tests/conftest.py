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
        self.filters: list[tuple[str, Any]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_error: Exception | None = None

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, self.table_data.get(name))

    def rpc(self, name: str, params: dict[str, Any]) -> "FakeQuery":
        self.rpc_calls.append((name, params))
        if self.rpc_error is not None:
            raise self.rpc_error
        return FakeQuery(self, None)


class FakeQuery:
    def __init__(self, fake: FakeSupabase, data: Any) -> None:
        self._fake = fake
        self._data = data

    def select(self, *columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._fake.filters.append((column, value))
        return self

    def limit(self, count: int) -> "FakeQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self._fake.filters.append(("order", column))
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
