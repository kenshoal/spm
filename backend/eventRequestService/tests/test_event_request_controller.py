from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(database_path: Path) -> TestClient:
    return TestClient(create_app(database_path))


def organiser_headers(organiser_id: str = "organiser-1") -> dict[str, str]:
    return {"X-Organiser-Id": organiser_id}


def test_health(tmp_path: Path) -> None:
    with make_client(tmp_path / "health.db") as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "eventRequestService",
        "status": "ok",
    }


def test_create_and_get_incomplete_draft(tmp_path: Path) -> None:
    with make_client(tmp_path / "create.db") as client:
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


def test_list_returns_only_the_current_organisers_requests(tmp_path: Path) -> None:
    with make_client(tmp_path / "list.db") as client:
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


def test_patch_updates_the_same_draft_and_can_clear_a_field(tmp_path: Path) -> None:
    with make_client(tmp_path / "update.db") as client:
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


def test_delete_removes_the_draft(tmp_path: Path) -> None:
    with make_client(tmp_path / "delete.db") as client:
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


def test_other_organiser_cannot_read_update_or_delete(tmp_path: Path) -> None:
    with make_client(tmp_path / "ownership.db") as client:
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


def test_requires_non_blank_organiser_header(tmp_path: Path) -> None:
    with make_client(tmp_path / "header.db") as client:
        missing = client.get("/event-requests")
        blank = client.get("/event-requests", headers={"X-Organiser-Id": " "})

    assert missing.status_code == 422
    assert blank.status_code == 422


def test_rejects_invalid_expected_attendance(tmp_path: Path) -> None:
    with make_client(tmp_path / "validation.db") as client:
        response = client.post(
            "/event-requests",
            headers=organiser_headers(),
            json={"expected_attendance": 0},
        )

    assert response.status_code == 422


def test_draft_persists_when_the_application_restarts(tmp_path: Path) -> None:
    database_path = tmp_path / "persistence.db"
    with make_client(database_path) as first_client:
        created = first_client.post(
            "/event-requests",
            headers=organiser_headers(),
            json={"description": "Persist this value"},
        ).json()

    with make_client(database_path) as restarted_client:
        response = restarted_client.get(
            f"/event-requests/{created['id']}",
            headers=organiser_headers(),
        )

    assert response.status_code == 200
    assert response.json()["description"] == "Persist this value"

