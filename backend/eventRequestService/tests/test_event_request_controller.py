from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import Header
from fastapi.testclient import TestClient

from app.controllers.event_request_controller import get_organiser_id
from app.main import create_app


class FakeEventRequestRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        row = {
            **values,
            "id": str(uuid4()),
            "created_at": now,
            "updated_at": now,
        }
        self.rows[row["id"]] = row
        return dict(row)

    def list_for_temporary_organiser(
        self, organiser_id: str
    ) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in reversed(list(self.rows.values()))
            if row["temporary_organiser_id"] == organiser_id
        ]

    def get_for_temporary_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if row is None or row["temporary_organiser_id"] != organiser_id:
            return None
        return dict(row)

    def update_for_temporary_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["temporary_organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return None
        row.update(values)
        row["updated_at"] = datetime.now(UTC).isoformat()
        return dict(row)

    def delete_for_temporary_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> bool:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["temporary_organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return False
        del self.rows[event_request_id]
        return True


def make_client(
    repository: FakeEventRequestRepository | None = None,
) -> TestClient:
    app = create_app(repository or FakeEventRequestRepository())

    def fake_organiser_id(authorization: str = Header()) -> str:
        return authorization.removeprefix("Bearer ")

    app.dependency_overrides[get_organiser_id] = fake_organiser_id
    return TestClient(app)


def organiser_headers(organiser_id: str = "organiser-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {organiser_id}"}


# Purpose: Confirms the service exposes a basic readiness signal.
def test_health() -> None:
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "eventRequestService",
        "status": "ok",
    }


# Purpose: Proves an organiser can save and retrieve an intentionally incomplete draft.
def test_create_and_get_incomplete_draft() -> None:
    with make_client() as client:
        created = client.post(
            "/event-requests",
            headers=organiser_headers(),
            json={"event_name": "Community Dinner"},
        )
        event_request_id = created.json()["id"]
        fetched = client.get(
            f"/event-requests/{event_request_id}",
            headers=organiser_headers(),
        )

    assert created.status_code == 201
    assert created.json()["status"] == "Draft"
    assert created.json()["event_name"] == "Community Dinner"
    assert created.json()["purpose"] is None
    assert fetched.status_code == 200
    assert fetched.json() == created.json()


# Purpose: Proves every SCRUM-8 field can be saved and retrieved without value loss.
def test_all_draft_fields_round_trip_unchanged() -> None:
    payload = {
        "event_name": "Community Technology Workshop",
        "purpose": "Teach practical skills",
        "description": "A hands-on community programme",
        "proposed_date_times": [
            "2026-10-20T10:00:00+08:00",
            "2026-10-21T14:30:00+08:00",
        ],
        "expected_attendance": 80,
        "venue_requirements": "Classroom with movable tables",
        "accessibility_needs": "Wheelchair-accessible route",
        "equipment_requirements": "Projector and two microphones",
        "registration_needs": "Online registration and check-in desk",
    }

    with make_client() as client:
        created = client.post(
            "/event-requests",
            headers=organiser_headers(),
            json=payload,
        )
        fetched = client.get(
            f"/event-requests/{created.json()['id']}",
            headers=organiser_headers(),
        )

    assert created.status_code == 201
    assert created.json()["status"] == "Draft"
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    for field, value in payload.items():
        if field == "proposed_date_times":
            assert len(created.json()[field]) == len(value)
        else:
            assert created.json()[field] == value


# Purpose: Protects draft privacy by keeping each organiser's list isolated.
def test_list_returns_only_the_current_organisers_requests() -> None:
    with make_client() as client:
        client.post(
            "/event-requests",
            headers=organiser_headers("organiser-1"),
            json={"event_name": "Visible event"},
        )
        client.post(
            "/event-requests",
            headers=organiser_headers("organiser-2"),
            json={"event_name": "Hidden event"},
        )
        response = client.get(
            "/event-requests", headers=organiser_headers("organiser-1")
        )

    assert response.status_code == 200
    assert [item["event_name"] for item in response.json()] == ["Visible event"]


# Purpose: Proves reopening a draft updates the same record and supports clearing fields.
def test_patch_updates_the_same_draft_and_can_clear_a_field() -> None:
    with make_client() as client:
        created = client.post(
            "/event-requests",
            headers=organiser_headers(),
            json={"event_name": "Original", "purpose": "Initial purpose"},
        ).json()
        response = client.patch(
            f"/event-requests/{created['id']}",
            headers=organiser_headers(),
            json={"event_name": "Updated", "purpose": ""},
        )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["event_name"] == "Updated"
    assert response.json()["purpose"] is None


# Purpose: Confirms an organiser can discard a draft and it is no longer retrievable.
def test_delete_removes_the_draft() -> None:
    with make_client() as client:
        created = client.post(
            "/event-requests",
            headers=organiser_headers(),
            json={},
        ).json()
        deleted = client.delete(
            f"/event-requests/{created['id']}",
            headers=organiser_headers(),
        )
        fetched = client.get(
            f"/event-requests/{created['id']}",
            headers=organiser_headers(),
        )

    assert deleted.status_code == 204
    assert fetched.status_code == 404


# Purpose: Prevents one organiser from viewing or changing another organiser's draft.
def test_other_organiser_cannot_read_update_or_delete() -> None:
    with make_client() as client:
        created = client.post(
            "/event-requests",
            headers=organiser_headers("owner"),
            json={"event_name": "Private draft"},
        ).json()
        path = f"/event-requests/{created['id']}"
        other_headers = organiser_headers("another-organiser")

        fetched = client.get(path, headers=other_headers)
        updated = client.patch(path, headers=other_headers, json={"event_name": "X"})
        deleted = client.delete(path, headers=other_headers)

    assert fetched.status_code == 404
    assert updated.status_code == 404
    assert deleted.status_code == 404


# Purpose: Ensures protected draft operations reject missing and malformed sessions.
def test_requires_bearer_session() -> None:
    with TestClient(create_app(FakeEventRequestRepository())) as client:
        missing = client.get("/event-requests")
        blank = client.get("/event-requests", headers={"Authorization": "Bearer "})
        wrong_scheme = client.get(
            "/event-requests", headers={"Authorization": "Basic token"}
        )

    assert missing.status_code == 401
    assert blank.status_code == 401
    assert wrong_scheme.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/event-requests"),
        ("POST", "/event-requests"),
        ("GET", "/event-requests/00000000-0000-0000-0000-000000000001"),
        ("PATCH", "/event-requests/00000000-0000-0000-0000-000000000001"),
        ("DELETE", "/event-requests/00000000-0000-0000-0000-000000000001"),
    ],
)
def test_every_draft_operation_rejects_unauthenticated_requests(
    method: str, path: str
) -> None:
    with TestClient(create_app(FakeEventRequestRepository())) as client:
        response = client.request(method, path, json={} if method in {"POST", "PATCH"} else None)

    assert response.status_code == 401


# Purpose: Refuses an identity supplied by the browser in place of a session.
def test_organiser_header_cannot_bypass_authentication() -> None:
    with TestClient(create_app(FakeEventRequestRepository())) as client:
        response = client.get(
            "/event-requests",
            headers={"X-Organiser-Id": "organiser,or(status.eq.Submitted)"},
        )

    assert response.status_code == 401


# Purpose: Binds all draft operations to the identity verified by authService.
def test_verified_identity_overrides_spoofed_header(monkeypatch: Any) -> None:
    organiser_id = str(uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(200, json={"id": organiser_id}),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        with TestClient(create_app(FakeEventRequestRepository())) as client:
            created = client.post(
                "/event-requests",
                headers={
                    "Authorization": "Bearer valid-token",
                    "X-Organiser-Id": "attacker",
                },
                json={},
            )
    finally:
        get_settings.cache_clear()

    assert created.status_code == 201
    assert created.json()["organiser_id"] == organiser_id


# Purpose: Rejects invalid or expired sessions before reading protected drafts.
def test_invalid_session_is_rejected(monkeypatch: Any) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(401, json={"detail": "Invalid session"}),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        with TestClient(create_app(FakeEventRequestRepository())) as client:
            response = client.get(
                "/event-requests", headers={"Authorization": "Bearer expired"}
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401


# Purpose: Prevents an invalid attendance value from being persisted in a draft.
def test_rejects_invalid_expected_attendance() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests",
            headers=organiser_headers(),
            json={"expected_attendance": 0},
        )

    assert response.status_code == 422


# Purpose: Proves saved values survive a new application instance using the same repository.
def test_draft_persists_when_the_application_restarts() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as first_client:
        created = first_client.post(
            "/event-requests",
            headers=organiser_headers(),
            json={"description": "Persist this value"},
        ).json()

    with make_client(repository) as restarted_client:
        response = restarted_client.get(
            f"/event-requests/{created['id']}",
            headers=organiser_headers(),
        )

    assert response.status_code == 200
    assert response.json()["description"] == "Persist this value"
