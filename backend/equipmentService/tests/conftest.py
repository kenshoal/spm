from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from requirements_support import C1, FakeEventService, RequirementsStore

from app.config import get_settings
from app.db import get_client
from app.event_requests_client import get_event_request_client
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
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_error: Exception | None = None
        self.rpc_result: Any = None
        self.table_errors: dict[str, Exception] = {}
        self.tables_queried: list[str] = []

    def table(self, name: str) -> "FakeQuery":
        self.tables_queried.append(name)
        return FakeQuery(self, self.table_data.get(name), self.table_errors.get(name))

    def rpc(self, name: str, params: dict[str, Any]) -> "FakeQuery":
        self.rpc_calls.append((name, params))
        if self.rpc_error is not None:
            raise self.rpc_error
        return FakeQuery(self, self.rpc_result)


class FakeQuery:
    def __init__(
        self, fake: FakeSupabase, data: Any, error: Exception | None = None
    ) -> None:
        self._fake = fake
        self._data = data
        self._error = error

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

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self._fake.filters.append((column, "in", list(values)))
        return self

    def lte(self, column: str, value: Any) -> "FakeQuery":
        self._fake.filters.append((column, "lte", value))
        return self

    def gte(self, column: str, value: Any) -> "FakeQuery":
        self._fake.filters.append((column, "gte", value))
        return self

    def limit(self, count: int) -> "FakeQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self._fake.filters.append(("order", column))
        return self

    def single(self) -> "FakeQuery":
        return self

    def execute(self) -> FakeResponse:
        if self._error is not None:
            raise self._error
        return FakeResponse(self._data)


@pytest.fixture
def fake_client() -> FakeSupabase:
    return FakeSupabase()


def _mock_auth(monkeypatch: pytest.MonkeyPatch, role: str, roles: list[str] | None = None) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200, json={"id": USER_ID, "role": role, "roles": roles or [role]}
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
def auth_attendee(monkeypatch: pytest.MonkeyPatch):
    _mock_auth(monkeypatch, "attendee")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def auth_manager_staff(monkeypatch: pytest.MonkeyPatch):
    _mock_auth(
        monkeypatch,
        "event_operations_manager",
        ["event_operations_manager", "technical_support"],
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(fake_client: FakeSupabase) -> TestClient:
    app.dependency_overrides[get_client] = lambda: fake_client
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# --- SCRUM-33 equipment requirements -------------------------------------


@pytest.fixture
def req_store() -> RequirementsStore:
    return RequirementsStore()


@pytest.fixture
def req_events() -> FakeEventService:
    return FakeEventService()


@pytest.fixture
def as_user(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Fake authService ``/auth/me``: ``as_user("event_coordinator")`` or
    ``as_user("event_organiser", "event_coordinator", user_id=C2)``. Any other
    ``httpx.get`` fails the test: the event client must not use it."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    get_settings.cache_clear()

    def set_user(*roles: str, user_id: str = C1) -> None:
        def fake_get(url: Any, *args: Any, **kwargs: Any) -> httpx.Response:
            assert str(url).endswith("/auth/me"), f"unexpected httpx.get {url}"
            return httpx.Response(
                200, json={"id": user_id, "role": roles[0], "roles": list(roles)}
            )

        monkeypatch.setattr(httpx, "get", fake_get)

    yield set_user
    get_settings.cache_clear()


@pytest.fixture
def req_api(
    req_store: RequirementsStore, req_events: FakeEventService
) -> Iterator[TestClient]:
    app.dependency_overrides[get_client] = lambda: req_store
    app.dependency_overrides[get_event_request_client] = req_events.client
    yield TestClient(app)
    app.dependency_overrides.clear()
