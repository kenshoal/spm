from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_client
from app.main import app

USER_ID = "11111111-1111-1111-1111-111111111111"


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


def _mock_auth(monkeypatch: pytest.MonkeyPatch, role: str) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200, json={"id": USER_ID, "role": role}
        ),
    )


@pytest.fixture
def auth(monkeypatch: pytest.MonkeyPatch):
    _mock_auth(monkeypatch, "event_coordinator")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def auth_staff(monkeypatch: pytest.MonkeyPatch):
    _mock_auth(monkeypatch, "technical_support")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(fake_client: FakeSupabase) -> TestClient:
    app.dependency_overrides[get_client] = lambda: fake_client
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
