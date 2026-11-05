"""/auth/me remembers a verified result briefly (perf/auth-verification-caching).

Every service calls /auth/me on every request. These tests pin that a repeat
call within the window skips Supabase, that the window never outlives the
token, that failures are never remembered, and that a role change through
this service takes effect at once. See app/token_cache.py.
"""

import base64
import json
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

from app import main
from app.integrations import get_supabase_verifier_client
from app.integrations import supabase as supabase_integration
from app.main import app, get_admin_client, get_optional_admin_client
from app.token_cache import TTL_SECONDS, VerifiedUserCache, token_expiry

NOW = 1_800_000_000.0


def jwt(exp: object, sub: str = "user-id") -> str:
    """A token shaped like a JWT. Supabase (mocked) does the real checks."""

    def part(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{part({'alg': 'ES256'})}.{part({'sub': sub, 'exp': exp})}.signature"


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(main, "verified_users", VerifiedUserCache(clock=clock))
    return clock


@pytest.fixture
def supabase(clock: Clock) -> Iterator[Mock]:
    supabase = Mock()
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-id", email="member@example.com", app_metadata={"role": "admin"}
        )
    )
    app.dependency_overrides[get_supabase_verifier_client] = lambda: supabase
    app.dependency_overrides[get_optional_admin_client] = lambda: None
    yield supabase
    app.dependency_overrides.clear()


def me(client: TestClient, token: str):
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})


# PERF-AUTH-H1 (happy): a repeat call with the same token inside the window
# returns the same identity without asking Supabase again, still no-store.
def test_repeat_call_is_served_without_supabase(
    client: TestClient, supabase: Mock
) -> None:
    token = jwt(NOW + 3600)

    first = me(client, token)
    second = me(client, token)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json() == {
        "id": "user-id",
        "email": "member@example.com",
        "role": "admin",
        "roles": ["admin"],
    }
    assert second.headers["cache-control"] == "no-store"
    supabase.auth.get_user.assert_called_once_with(token)


# PERF-AUTH-P1 (partition): different tokens are verified separately.
def test_different_tokens_are_verified_separately(
    client: TestClient, supabase: Mock
) -> None:
    me(client, jwt(NOW + 3600, sub="a"))
    me(client, jwt(NOW + 3600, sub="b"))

    assert supabase.auth.get_user.call_count == 2


# PERF-AUTH-B1/B2/B3 (boundary): just inside the window the result is reused;
# at and just past the window Supabase is asked again.
@pytest.mark.parametrize(
    ("elapsed", "expected_calls"),
    [(TTL_SECONDS - 0.001, 1), (TTL_SECONDS, 2), (TTL_SECONDS + 0.001, 2)],
)
def test_window_boundary(
    client: TestClient,
    supabase: Mock,
    clock: Clock,
    elapsed: float,
    expected_calls: int,
) -> None:
    token = jwt(NOW + 3600)
    me(client, token)

    clock.now = NOW + elapsed
    me(client, token)

    assert supabase.auth.get_user.call_count == expected_calls


# PERF-AUTH-B4 (boundary): a token expiring before the window ends is only
# remembered until its own exp.
def test_entry_never_outlives_the_token(
    client: TestClient, supabase: Mock, clock: Clock
) -> None:
    token = jwt(NOW + 5)
    me(client, token)

    clock.now = NOW + 4.999
    me(client, token)
    assert supabase.auth.get_user.call_count == 1

    clock.now = NOW + 5
    me(client, token)
    assert supabase.auth.get_user.call_count == 2


# PERF-AUTH-N1 (negative): a token whose exp cannot be read is never
# remembered, so every call is verified by Supabase.
@pytest.mark.parametrize(
    "token",
    ["access-token", jwt("soon"), jwt(True), "a.%%%.c", jwt(NOW - 1)],
)
def test_unreadable_or_expired_exp_is_not_remembered(
    client: TestClient, supabase: Mock, token: str
) -> None:
    me(client, token)
    me(client, token)

    assert supabase.auth.get_user.call_count == 2


# PERF-AUTH-N2 (negative): a refused token is not remembered; the next call
# is checked again and a now-valid answer is returned.
def test_refused_token_is_not_remembered(
    client: TestClient, supabase: Mock
) -> None:
    token = jwt(NOW + 3600)
    valid = supabase.auth.get_user.return_value
    supabase.auth.get_user.side_effect = [
        AuthApiError("expired", 401, "bad_jwt"),
        valid,
    ]

    assert me(client, token).status_code == 401
    assert me(client, token).status_code == 200
    assert supabase.auth.get_user.call_count == 2


# PERF-AUTH-N3 (negative): a malformed header is refused before the cache or
# Supabase is consulted.
def test_malformed_header_is_refused_first(
    client: TestClient, supabase: Mock
) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Token abc"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    supabase.auth.get_user.assert_not_called()
    assert len(main.verified_users) == 0


# PERF-AUTH-X1 (cross-cutting): a role change through this service clears the
# target user's remembered identity, so their next /auth/me shows new roles.
def test_role_change_clears_remembered_identity(
    client: TestClient, supabase: Mock
) -> None:
    member_token = jwt(NOW + 3600, sub="member-id")
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="member-id", email="m@example.com", app_metadata={"role": "attendee"}
        )
    )
    assert me(client, member_token).json()["roles"] == ["attendee"]

    admin = Mock()
    app.dependency_overrides[get_admin_client] = lambda: admin
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="admin-id", email="a@example.com", app_metadata={"role": "admin"}
        )
    )
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "admin"}]),
        SimpleNamespace(data=[{"role": "technical_support"}]),
    ]
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(id="member-id", email="m@example.com", app_metadata={})
    )
    assert (
        client.patch(
            "/auth/users/member-id/role",
            headers={"Authorization": "Bearer admin-token"},
            json={"role": "technical_support"},
        ).status_code
        == 200
    )

    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="member-id",
            email="m@example.com",
            app_metadata={"role": "technical_support"},
        )
    )
    assert me(client, member_token).json()["roles"] == ["technical_support"]


# PERF-AUTH-X2 (cross-cutting): clearing one user's entries leaves others.
def test_invalidate_user_only_drops_that_user() -> None:
    cache: VerifiedUserCache[str] = VerifiedUserCache(clock=lambda: NOW)
    cache.put(jwt(NOW + 60, "a"), "a", "A")
    cache.put(jwt(NOW + 60, "b"), "b", "B")

    cache.invalidate_user("a")

    assert cache.get(jwt(NOW + 60, "a")) is None
    assert cache.get(jwt(NOW + 60, "b")) == "B"


# PERF-AUTH-B5 (boundary): at the size cap, expired entries are dropped first
# and live ones kept; the cache never grows past the cap.
def test_size_cap_drops_expired_entries_first() -> None:
    clock = Clock()
    cache: VerifiedUserCache[str] = VerifiedUserCache(max_entries=2, clock=clock)
    cache.put(jwt(NOW + 1, "old"), "old", "OLD")
    cache.put(jwt(NOW + 60, "live"), "live", "LIVE")
    clock.now = NOW + 2

    cache.put(jwt(NOW + 60, "new"), "new", "NEW")

    assert len(cache) == 2
    assert cache.get(jwt(NOW + 60, "live")) == "LIVE"
    assert cache.get(jwt(NOW + 60, "new")) == "NEW"


# PERF-AUTH-P2 (partition): token_expiry reads a numeric exp and rejects
# anything else.
@pytest.mark.parametrize(
    ("token", "expected"),
    [
        (jwt(1234), 1234.0),
        (jwt(12.5), 12.5),
        (jwt(None), None),
        (jwt(False), None),
        ("no-dots", None),
        ("a.!!!.c", None),
    ],
)
def test_token_expiry(token: str, expected: float | None) -> None:
    assert token_expiry(token) == expected


# PERF-AUTH-X3 (cross-cutting): the verifier and admin clients are built once
# and reused, while sign-in still gets a fresh client per call.
def test_verifier_and_admin_clients_are_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    create_client = Mock(side_effect=lambda *_: object())
    monkeypatch.setattr(supabase_integration, "create_client", create_client)
    get_settings.cache_clear()

    try:
        verifier = supabase_integration.get_supabase_verifier_client()
        assert supabase_integration.get_supabase_verifier_client() is verifier
        admin = supabase_integration.get_supabase_admin_client()
        assert supabase_integration.get_supabase_admin_client() is admin
        assert (
            supabase_integration.get_supabase_client()
            is not supabase_integration.get_supabase_client()
        )
        assert create_client.call_count == 4
    finally:
        get_settings.cache_clear()
