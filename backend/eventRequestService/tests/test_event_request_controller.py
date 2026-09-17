from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.controllers import event_request_controller
from app.main import create_app


class FakeEventRequestRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
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
        if row is None or row["organiser_id"] != organiser_id or row["status"] != "Draft":
            return None
        row.update(values)
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(row)

    def submit_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if row is None or row["organiser_id"] != organiser_id or row["status"] != "Draft":
            return None
        row.update(values)
        row["status"] = "Submitted"
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(row)

    def delete_for_organiser(self, event_request_id: str, organiser_id: str) -> bool:
        row = self.rows.get(event_request_id)
        if row is None or row["organiser_id"] != organiser_id or row["status"] != "Draft":
            return False
        del self.rows[event_request_id]
        return True


ORGANISER_ID = "11111111-1111-4111-8111-111111111111"
AUTH_TOKEN = "valid-token"


def authenticated_client(repository: FakeEventRequestRepository) -> TestClient:
    application = create_app(repository)
    application.dependency_overrides[event_request_controller.get_organiser_id] = (
        lambda: ORGANISER_ID
    )
    return TestClient(application)


def test_create_uses_authenticated_organiser_id() -> None:
    repository = FakeEventRequestRepository()
    client = authenticated_client(repository)

    response = client.post(
        "/event-requests",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        json={"event_name": "Community Dinner"},
    )

    assert response.status_code == 201
    assert response.json()["organiser_id"] == ORGANISER_ID


def test_update_is_scoped_to_authenticated_organiser() -> None:
    repository = FakeEventRequestRepository()
    client = authenticated_client(repository)
    created = repository.create(
        {"organiser_id": ORGANISER_ID, "status": "Draft", "event_name": "Original"}
    )

    response = client.patch(
        f"/event-requests/{created['id']}",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        json={"event_name": "Updated"},
    )

    assert response.status_code == 200
    assert response.json()["organiser_id"] == ORGANISER_ID
    assert response.json()["event_name"] == "Updated"


def test_request_cannot_be_updated_by_another_organiser() -> None:
    repository = FakeEventRequestRepository()
    client = authenticated_client(repository)
    created = repository.create(
        {
            "organiser_id": "22222222-2222-4222-8222-222222222222",
            "status": "Draft",
            "event_name": "Private event",
        }
    )

    response = client.patch(
        f"/event-requests/{created['id']}",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        json={"event_name": "Should not change"},
    )

    assert response.status_code == 404