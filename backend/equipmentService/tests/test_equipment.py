from typing import Any

from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
EQUIPMENT_ID = "22222222-2222-2222-2222-222222222222"

EQUIPMENT_ROW: dict[str, Any] = {
    "id": EQUIPMENT_ID,
    "type": "Speaker",
    "description": "PA speaker",
    "total_owned_quantity": 4,
    "home_location": "Store Room B",
    "operational_status": "AVAILABLE",
    "created_by": USER_ID,
    "created_at": "2026-09-15T09:00:00+00:00",
    "updated_at": "2026-09-15T09:00:00+00:00",
}


def test_hello(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "equipmentService",
        "message": "Hello from equipmentService",
    }


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "equipmentService",
        "status": "ok",
    }


def test_list_equipment(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get("/equipment")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == EQUIPMENT_ID
    assert body[0]["operational_status"] == "AVAILABLE"


def test_list_equipment_filters(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get(
        "/equipment",
        params={"type": "Speaker", "operational_status": "AVAILABLE"},
    )

    assert response.status_code == 200
    assert ("type", "Speaker") in fake_client.filters
    assert ("operational_status", "AVAILABLE") in fake_client.filters


def test_list_equipment_invalid_status_filter(client: TestClient) -> None:
    response = client.get("/equipment", params={"operational_status": "BOGUS"})

    assert response.status_code == 422


def test_get_equipment(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get(f"/equipment/{EQUIPMENT_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == EQUIPMENT_ID


def test_get_equipment_not_found(
    client: TestClient
) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}")

    assert response.status_code == 404


def test_get_equipment_invalid_id(client: TestClient) -> None:
    response = client.get("/equipment/not-a-uuid")

    assert response.status_code == 422


def test_create_equipment(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [dict(EQUIPMENT_ROW)]

    response = client.post(
        "/equipment",
        headers={"X-User-Id": USER_ID},
        json={
            "type": "Speaker",
            "description": "PA speaker",
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == EQUIPMENT_ID

    equipment_inserts = [
        i for i in fake_client.inserts if "home_location" in i
    ]
    assert len(equipment_inserts) == 1
    assert equipment_inserts[0]["created_by"] == USER_ID
    assert equipment_inserts[0]["operational_status"] == "AVAILABLE"

    history_inserts = [
        i for i in fake_client.inserts if "equipment_id" in i
    ]
    assert len(history_inserts) == 1
    assert history_inserts[0]["old_status"] is None
    assert history_inserts[0]["new_status"] == "AVAILABLE"
    assert history_inserts[0]["changed_by"] == USER_ID


def test_create_equipment_requires_user(client: TestClient) -> None:
    response = client.post(
        "/equipment",
        json={
            "type": "Speaker",
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 401


def test_create_equipment_negative_quantity(client: TestClient) -> None:
    response = client.post(
        "/equipment",
        headers={"X-User-Id": USER_ID},
        json={
            "type": "Speaker",
            "total_owned_quantity": -1,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 422


def test_update_quantity(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [
        {**EQUIPMENT_ROW, "total_owned_quantity": 6}
    ]

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers={"X-User-Id": USER_ID},
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 200
    assert response.json()["total_owned_quantity"] == 6
    assert len(fake_client.updates) == 1
    assert fake_client.updates[0]["total_owned_quantity"] == 6
    assert ("id", EQUIPMENT_ID) in fake_client.filters


def test_update_quantity_requires_user(client: TestClient) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 401


def test_update_quantity_negative(client: TestClient) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers={"X-User-Id": USER_ID},
        json={"total_owned_quantity": -3},
    )

    assert response.status_code == 422


def test_update_quantity_not_found(client: TestClient, fake_client) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers={"X-User-Id": USER_ID},
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 404
