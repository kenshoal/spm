from collections.abc import Iterator

import httpx2
import pytest
from fakes import FakeNotificationRepository
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

USER_ID = "9e96871b-63de-4083-8812-49d75788e5ba"


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("AUTH_SERVICE_URL", "http://auth.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def auth_service_answers(
    monkeypatch: pytest.MonkeyPatch, response: httpx2.Response
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx2.Response:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return response

    monkeypatch.setattr(httpx2, "get", fake_get)
    return captured


def inbox_status(authorization: str | None) -> int:
    headers = {} if authorization is None else {"Authorization": authorization}
    with TestClient(create_app(FakeNotificationRepository())) as client:
        return client.get("/notifications", headers=headers).status_code


# Purpose: The inbox trusts only the identity authService verifies for the token.
def test_uses_the_user_id_authservice_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = auth_service_answers(
        monkeypatch,
        httpx2.Response(200, json={"id": USER_ID, "role": "event_coordinator"}),
    )
    repository = FakeNotificationRepository()
    repository.save(
        event_type="coordinator_assigned",
        recipient_id=USER_ID,
        payload={},
        event_id=None,
    )
    with TestClient(create_app(repository)) as client:
        response = client.get(
            "/notifications", headers={"Authorization": "Bearer valid-token"}
        )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert captured == {
        "url": "http://auth.test/auth/me",
        "headers": {"Authorization": "Bearer valid-token"},
    }


# Purpose: The scheme name is case-insensitive in HTTP, and login answers
# "token_type": "bearer", so a lowercase scheme must work too.
def test_accepts_a_lowercase_bearer_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_service_answers(monkeypatch, httpx2.Response(200, json={"id": USER_ID}))

    assert inbox_status("bearer valid-token") == 200


# Purpose: Swagger UI never sends a header parameter named Authorization, so the
# API docs must declare a bearer security scheme to get an Authorize button
# that does send the token.
def test_api_docs_declare_bearer_sign_in() -> None:
    schema = create_app(FakeNotificationRepository()).openapi()

    schemes = schema["components"]["securitySchemes"].values()
    assert {"type": "http", "scheme": "bearer"}.items() <= next(iter(schemes)).items()
    for path, method in [
        ("/notifications", "get"),
        ("/notifications/{notification_id}/read", "patch"),
    ]:
        assert schema["paths"][path][method]["security"], path
    assert "security" not in schema["paths"]["/notifications/events"]["post"]


# Purpose: Requests without a well-formed bearer token never reach authService.
@pytest.mark.parametrize(
    "authorization", [None, "", "Basic abc", "Bearer ", "Bearer two parts"]
)
def test_rejects_a_missing_or_malformed_token(
    monkeypatch: pytest.MonkeyPatch, authorization: str | None
) -> None:
    captured = auth_service_answers(monkeypatch, httpx2.Response(200, json={}))

    assert inbox_status(authorization) == 401
    assert captured == {}


# Purpose: An expired or invalid session is refused.
def test_rejects_a_session_authservice_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_service_answers(monkeypatch, httpx2.Response(401, json={"detail": "no"}))

    assert inbox_status("Bearer expired") == 401


# Purpose: authService being down is a gateway failure, not the caller's fault.
def test_reports_authservice_outage_as_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(url: str, **kwargs: object) -> httpx2.Response:
        raise httpx2.ConnectError("down")

    monkeypatch.setattr(httpx2, "get", unreachable)

    assert inbox_status("Bearer valid-token") == 502


# Purpose: A reply without a usable user id is never treated as a signed-in user.
@pytest.mark.parametrize(
    "body", [{}, {"id": "not-a-uuid"}, {"id": None}, ["not", "an", "object"]]
)
def test_rejects_a_reply_without_a_user_id(
    monkeypatch: pytest.MonkeyPatch, body: object
) -> None:
    auth_service_answers(monkeypatch, httpx2.Response(200, json=body))

    assert inbox_status("Bearer valid-token") == 502
