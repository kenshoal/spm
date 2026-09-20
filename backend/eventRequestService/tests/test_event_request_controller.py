from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.controllers import event_request_controller
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

    def list_for_organiser(self, organiser_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in reversed(list(self.rows.values()))
            if row["organiser_id"] == organiser_id
        ]

    def get_for_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if row is None or row["organiser_id"] != organiser_id:
            return None
        return dict(row)

    def update_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return None
        row.update(values)
        row["updated_at"] = datetime.now(UTC).isoformat()
        return dict(row)

    def submit_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return None
        row.update(values)
        row["status"] = "Submitted"
        row["updated_at"] = datetime.now(UTC).isoformat()
        return dict(row)

    def delete_for_organiser(self, event_request_id: str, organiser_id: str) -> bool:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return False
        del self.rows[event_request_id]
        return True


ORGANISER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ORGANISER_ID = "22222222-2222-4222-8222-222222222222"


def make_client(
    repository: FakeEventRequestRepository | None = None,
    organiser_id: str = ORGANISER_ID,
) -> TestClient:
    application = create_app(repository or FakeEventRequestRepository())
    application.dependency_overrides[event_request_controller.get_organiser_id] = (
        lambda: organiser_id
    )
    return TestClient(application)


def complete_payload() -> dict[str, object]:
    return {
        "event_name": "Community Technology Workshop",
        "purpose": "Teach practical skills",
        "description": "A hands-on community programme",
        "proposed_date_times": ["2026-10-20T10:00:00+08:00"],
        "expected_attendance": 80,
        "venue_requirements": "Classroom with movable tables",
        "accessibility_needs": "No special requirements",
        "equipment_requirements": "Projector and two microphones",
        "registration_needs": "Online registration and check-in desk",
    }


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
            json={"event_name": "Community Dinner"},
        )
        fetched = client.get(f"/event-requests/{created.json()['id']}")

    assert created.status_code == 201
    assert created.json()["status"] == "Draft"
    assert created.json()["organiser_id"] == ORGANISER_ID
    assert created.json()["purpose"] is None
    assert fetched.json() == created.json()


# Purpose: Proves every event-request field survives a draft round trip unchanged.
def test_all_draft_fields_round_trip_unchanged() -> None:
    payload = complete_payload()
    with make_client() as client:
        created = client.post("/event-requests", json=payload)
        fetched = client.get(f"/event-requests/{created.json()['id']}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    for field, value in payload.items():
        if field == "proposed_date_times":
            assert len(created.json()[field]) == len(value)  # type: ignore[arg-type]
        else:
            assert created.json()[field] == value


# Purpose: Protects request privacy by excluding records owned by another organiser.
def test_list_returns_only_the_current_organisers_requests() -> None:
    repository = FakeEventRequestRepository()
    repository.create(
        {"organiser_id": ORGANISER_ID, "status": "Draft", "event_name": "Visible"}
    )
    repository.create(
        {
            "organiser_id": OTHER_ORGANISER_ID,
            "status": "Draft",
            "event_name": "Hidden",
        }
    )

    with make_client(repository) as client:
        response = client.get("/event-requests")

    assert response.status_code == 200
    assert [item["event_name"] for item in response.json()] == ["Visible"]


# Purpose: Proves reopening a draft updates the same record and supports clearing fields.
def test_patch_updates_the_same_draft_and_can_clear_a_field() -> None:
    with make_client() as client:
        created = client.post(
            "/event-requests",
            json={"event_name": "Original", "purpose": "Initial purpose"},
        ).json()
        response = client.patch(
            f"/event-requests/{created['id']}",
            json={"event_name": "Updated", "purpose": ""},
        )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["event_name"] == "Updated"
    assert response.json()["purpose"] is None


# Purpose: Confirms an organiser can discard a Draft and cannot retrieve it afterwards.
def test_delete_removes_the_draft() -> None:
    with make_client() as client:
        created = client.post("/event-requests", json={}).json()
        deleted = client.delete(f"/event-requests/{created['id']}")
        fetched = client.get(f"/event-requests/{created['id']}")

    assert deleted.status_code == 204
    assert fetched.status_code == 404


# Purpose: Prevents one organiser from reading or mutating another organiser's Draft.
def test_other_organiser_cannot_read_update_or_delete() -> None:
    repository = FakeEventRequestRepository()
    created = repository.create(
        {
            "organiser_id": OTHER_ORGANISER_ID,
            "status": "Draft",
            "event_name": "Private draft",
        }
    )
    path = f"/event-requests/{created['id']}"

    with make_client(repository) as client:
        fetched = client.get(path)
        updated = client.patch(path, json={"event_name": "Changed"})
        deleted = client.delete(path)

    assert fetched.status_code == 404
    assert updated.status_code == 404
    assert deleted.status_code == 404
    assert repository.rows[created["id"]]["event_name"] == "Private draft"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/event-requests"),
        ("POST", "/event-requests"),
        ("POST", "/event-requests/submissions"),
        ("GET", "/event-requests/00000000-0000-0000-0000-000000000001"),
        ("PATCH", "/event-requests/00000000-0000-0000-0000-000000000001"),
        ("POST", "/event-requests/00000000-0000-0000-0000-000000000001/submit"),
        ("DELETE", "/event-requests/00000000-0000-0000-0000-000000000001"),
    ],
)
# Purpose: Ensures every event-request operation rejects a missing bearer session.
def test_every_operation_rejects_unauthenticated_requests(
    method: str, path: str
) -> None:
    with TestClient(create_app(FakeEventRequestRepository())) as client:
        response = client.request(
            method,
            path,
            json={} if method in {"POST", "PATCH"} else None,
        )

    assert response.status_code == 401


# Purpose: Refuses an organiser identity supplied by the browser instead of a session.
def test_organiser_header_cannot_bypass_authentication() -> None:
    with TestClient(create_app(FakeEventRequestRepository())) as client:
        response = client.get(
            "/event-requests",
            headers={"X-Organiser-Id": "attacker"},
        )

    assert response.status_code == 401


# Purpose: Binds stored ownership to the identity verified by authService.
def test_verified_identity_overrides_spoofed_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"id": ORGANISER_ID, "role": "organiser"},
        ),
    )
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
    assert created.json()["organiser_id"] == ORGANISER_ID


@pytest.mark.parametrize("role", [None, "admin", "operations_manager"])
# Purpose: Prevents authenticated non-organisers from accessing organiser requests.
def test_event_request_operations_require_organiser_role(
    monkeypatch: pytest.MonkeyPatch,
    role: str | None,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"id": ORGANISER_ID, "role": role},
        ),
    )
    get_settings.cache_clear()
    try:
        with TestClient(create_app(FakeEventRequestRepository())) as client:
            response = client.post(
                "/event-requests/submissions",
                headers={"Authorization": "Bearer valid-token"},
                json=complete_payload(),
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Event Organiser role required"}


# Purpose: Rejects invalid or expired sessions before protected data is accessed.
def test_invalid_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(401, json={"detail": "Invalid"}),
    )
    get_settings.cache_clear()
    try:
        with TestClient(create_app(FakeEventRequestRepository())) as client:
            response = client.get(
                "/event-requests",
                headers={"Authorization": "Bearer expired"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401


# Purpose: Prevents invalid attendance from being persisted in a Draft.
def test_rejects_invalid_expected_attendance() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests",
            json={"expected_attendance": 0},
        )

    assert response.status_code == 422


# Purpose: Proves a complete new form can enter coordination without a prior Draft.
def test_submit_complete_new_event_request_directly() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        response = client.post("/event-requests/submissions", json=complete_payload())

    assert response.status_code == 201
    assert response.json()["status"] == "Submitted"
    assert response.json()["organiser_id"] == ORGANISER_ID
    assert len(repository.rows) == 1


@pytest.mark.parametrize("missing_field", list(complete_payload()))
# Purpose: Prevents any incomplete new form from entering the coordination workflow.
def test_direct_submission_requires_every_form_field(missing_field: str) -> None:
    repository = FakeEventRequestRepository()
    payload = complete_payload()
    payload.pop(missing_field)

    with make_client(repository) as client:
        response = client.post("/event-requests/submissions", json=payload)

    assert response.status_code == 422
    assert repository.rows == {}


# Purpose: Moves the existing Draft to Submitted without creating a duplicate record.
def test_submit_completed_draft() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        created = client.post(
            "/event-requests", json={"event_name": "Initial title"}
        ).json()
        response = client.post(
            f"/event-requests/{created['id']}/submit",
            json=complete_payload(),
        )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["status"] == "Submitted"
    assert response.json()["event_name"] == complete_payload()["event_name"]
    assert len(repository.rows) == 1


# Purpose: Keeps an incomplete saved Draft editable when submission validation fails.
def test_incomplete_draft_remains_draft_after_rejected_submission() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        created = client.post(
            "/event-requests", json={"event_name": "Incomplete"}
        ).json()
        response = client.post(
            f"/event-requests/{created['id']}/submit",
            json={"event_name": "Incomplete"},
        )
        fetched = client.get(f"/event-requests/{created['id']}")

    assert response.status_code == 422
    assert fetched.json()["status"] == "Draft"
    assert fetched.json()["event_name"] == "Incomplete"


# Purpose: Prevents ambiguous local times from being persisted with the wrong offset.
def test_submission_requires_timezone_aware_dates() -> None:
    repository = FakeEventRequestRepository()
    payload = complete_payload()
    payload["proposed_date_times"] = ["2026-10-20T10:00:00"]

    with make_client(repository) as client:
        response = client.post("/event-requests/submissions", json=payload)

    assert response.status_code == 422
    assert repository.rows == {}


# Purpose: Prevents one organiser from submitting another organiser's Draft.
def test_other_organiser_cannot_submit_draft() -> None:
    repository = FakeEventRequestRepository()
    created = repository.create(
        {
            "organiser_id": OTHER_ORGANISER_ID,
            "status": "Draft",
            **complete_payload(),
        }
    )

    with make_client(repository) as client:
        response = client.post(
            f"/event-requests/{created['id']}/submit",
            json=complete_payload(),
        )

    assert response.status_code == 404
    assert repository.rows[created["id"]]["status"] == "Draft"


# Purpose: Prevents resubmission, editing and deletion after coordination begins.
def test_submitted_request_is_read_only() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        submitted = client.post(
            "/event-requests/submissions", json=complete_payload()
        ).json()
        path = f"/event-requests/{submitted['id']}"
        updated = client.patch(path, json={"event_name": "Changed"})
        resubmitted = client.post(f"{path}/submit", json=complete_payload())
        deleted = client.delete(path)
        fetched = client.get(path)

    assert updated.status_code == 409
    assert resubmitted.status_code == 409
    assert deleted.status_code == 409
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "Submitted"
    assert fetched.json()["event_name"] == complete_payload()["event_name"]
