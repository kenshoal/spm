from typing import Any

from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

USER_ID = "11111111-1111-1111-1111-111111111111"
EQUIPMENT_ID = "22222222-2222-2222-2222-222222222222"

EQUIPMENT_ROW: dict[str, Any] = {
    "id": EQUIPMENT_ID,
    "operational_status": "AVAILABLE",
}


def test_hello(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "equipmentStatusService",
        "message": "Hello from equipmentStatusService",
    }


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "equipmentStatusService",
        "status": "ok",
    }


def test_get_status_available(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get(f"/equipment/{EQUIPMENT_ID}/status")

    assert response.status_code == 200
    assert response.json() == {
        "equipment_id": EQUIPMENT_ID,
        "operational_status": "AVAILABLE",
        "available": True,
    }


def test_get_status_unavailable(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [
        {**EQUIPMENT_ROW, "operational_status": "DAMAGED"}
    ]

    response = client.get(f"/equipment/{EQUIPMENT_ID}/status")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_get_status_not_found(client: TestClient, fake_client) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}/status")

    assert response.status_code == 404


def test_transition_status(client: TestClient, fake_client) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers={"X-User-Id": USER_ID},
        json={"new_status": "DAMAGED", "reason": "Dropped during setup"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "equipment_id": EQUIPMENT_ID,
        "new_status": "DAMAGED",
        "changed_by": USER_ID,
        "reason": "Dropped during setup",
    }
    assert fake_client.rpc_calls == [
        (
            "transition_equipment_status",
            {
                "p_equipment_id": EQUIPMENT_ID,
                "p_new_status": "DAMAGED",
                "p_changed_by": USER_ID,
                "p_reason": "Dropped during setup",
            },
        )
    ]


def test_transition_status_requires_user(client: TestClient) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 401


def test_transition_status_invalid_status(client: TestClient) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers={"X-User-Id": USER_ID},
        json={"new_status": "ON_FIRE"},
    )

    assert response.status_code == 422


def test_transition_status_unknown_equipment(
    client: TestClient, fake_client
) -> None:
    fake_client.rpc_error = APIError(
        {"message": "equipment not found", "code": "P0001"}
    )

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers={"X-User-Id": USER_ID},
        json={"new_status": "RETIRED"},
    )

    assert response.status_code == 404


def test_transition_status_rpc_failure(
    client: TestClient, fake_client
) -> None:
    fake_client.rpc_error = APIError({"message": "database exploded"})

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers={"X-User-Id": USER_ID},
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 500


def test_status_history(client: TestClient, fake_client) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]
    fake_client.table_data["equipment_status_history"] = [
        {
            "id": 2,
            "equipment_id": EQUIPMENT_ID,
            "old_status": "DAMAGED",
            "new_status": "UNDER_REPAIR",
            "reason": "Sent to vendor",
            "changed_by": USER_ID,
            "changed_at": "2026-09-15T10:00:00+00:00",
        },
        {
            "id": 1,
            "equipment_id": EQUIPMENT_ID,
            "old_status": None,
            "new_status": "AVAILABLE",
            "reason": None,
            "changed_by": USER_ID,
            "changed_at": "2026-09-15T09:00:00+00:00",
        },
    ]

    response = client.get(f"/equipment/{EQUIPMENT_ID}/status/history")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == 2
    assert body[1]["old_status"] is None
    assert ("order", "changed_at") in fake_client.filters


def test_status_history_unknown_equipment(
    client: TestClient, fake_client
) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}/status/history")

    assert response.status_code == 404
