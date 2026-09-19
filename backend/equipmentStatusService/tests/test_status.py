from typing import Any

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

USER_ID = "11111111-1111-1111-1111-111111111111"
EQUIPMENT_ID = "22222222-2222-2222-2222-222222222222"

EQUIPMENT_ROW: dict[str, Any] = {
    "id": EQUIPMENT_ID,
    "operational_status": "AVAILABLE",
}


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


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


def test_get_status_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}/status")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization", ["Basic abc", "Bearer ", "Bearer a b", "Bearer"]
)
def test_get_status_rejects_malformed_bearer(
    client: TestClient, authorization: str
) -> None:
    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers={"Authorization": authorization},
    )

    assert response.status_code == 401


def test_get_status_available(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status", headers=bearer()
    )

    assert response.status_code == 200
    assert response.json() == {
        "equipment_id": EQUIPMENT_ID,
        "operational_status": "AVAILABLE",
        "available": True,
    }


def test_get_status_unavailable(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [
        {**EQUIPMENT_ROW, "operational_status": "DAMAGED"}
    ]

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status", headers=bearer()
    )

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_get_status_not_found(client: TestClient, fake_client, auth) -> None:
    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status", headers=bearer()
    )

    assert response.status_code == 404


def test_transition_status_requires_authentication(client: TestClient) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 401


def test_transition_status_forbidden_for_event_coordinator(
    client: TestClient, auth
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 403


def test_transition_status(client: TestClient, fake_client, auth_staff) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
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


def test_transition_status_invalid_status(
    client: TestClient, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "ON_FIRE"},
    )

    assert response.status_code == 422


def test_transition_status_without_reason(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "UNDER_REPAIR"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["new_status"] == "UNDER_REPAIR"
    assert body["reason"] is None
    assert fake_client.rpc_calls[0][1]["p_reason"] is None
    assert fake_client.rpc_calls[0][0] == "transition_equipment_status"


def test_transition_status_invalid_equipment_id(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        "/equipment/not-a-uuid/status",
        headers=bearer(),
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 422
    assert fake_client.rpc_calls == []


def test_transition_status_unknown_equipment(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_error = APIError(
        {"message": "equipment not found", "code": "P0001"}
    )

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "RETIRED"},
    )

    assert response.status_code == 404


def test_transition_status_rpc_failure(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_error = APIError({"message": "database exploded"})

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 500


def test_status_history_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}/status/history")

    assert response.status_code == 401


def test_status_history(client: TestClient, fake_client, auth) -> None:
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

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status/history", headers=bearer()
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == 2
    assert body[1]["old_status"] is None
    assert ("order", "changed_at") in fake_client.filters


def test_status_history_unknown_equipment(
    client: TestClient, fake_client, auth
) -> None:
    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status/history", headers=bearer()
    )

    assert response.status_code == 404


def test_status_history_empty(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]
    fake_client.table_data["equipment_status_history"] = []

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status/history", headers=bearer()
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_status_invalid_equipment_id(client: TestClient, auth) -> None:
    response = client.get("/equipment/not-a-uuid/status", headers=bearer())

    assert response.status_code == 422
