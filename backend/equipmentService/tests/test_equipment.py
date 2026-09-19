from typing import Any

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

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


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


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


def test_list_equipment_requires_authentication(client: TestClient) -> None:
    response = client.get("/equipment")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization", ["Basic abc", "Bearer ", "Bearer a b", "Bearer"]
)
def test_list_equipment_rejects_malformed_bearer(
    client: TestClient, authorization: str
) -> None:
    response = client.get("/equipment", headers={"Authorization": authorization})

    assert response.status_code == 401


def test_list_equipment(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get("/equipment", headers=bearer())

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == EQUIPMENT_ID
    assert body[0]["operational_status"] == "AVAILABLE"


def test_list_equipment_filters(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get(
        "/equipment",
        headers=bearer(),
        params={"type": "Speaker", "operational_status": "AVAILABLE"},
    )

    assert response.status_code == 200
    assert ("type", "Speaker") in fake_client.filters
    assert ("operational_status", "AVAILABLE") in fake_client.filters


def test_list_equipment_invalid_status_filter(
    client: TestClient, auth
) -> None:
    response = client.get(
        "/equipment", headers=bearer(), params={"operational_status": "BOGUS"}
    )

    assert response.status_code == 422


def test_get_equipment(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get(f"/equipment/{EQUIPMENT_ID}", headers=bearer())

    assert response.status_code == 200
    assert response.json()["id"] == EQUIPMENT_ID


def test_get_equipment_not_found(client: TestClient, auth) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}", headers=bearer())

    assert response.status_code == 404


def test_get_equipment_invalid_id(client: TestClient, auth) -> None:
    response = client.get("/equipment/not-a-uuid", headers=bearer())

    assert response.status_code == 422


def test_create_equipment_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/equipment",
        json={
            "type": "Speaker",
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 401


def test_create_equipment_forbidden_for_event_coordinator(
    client: TestClient, auth
) -> None:
    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "Speaker",
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 403


def test_create_equipment(client: TestClient, fake_client, auth_staff) -> None:
    fake_client.rpc_result = dict(EQUIPMENT_ROW)

    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "Speaker",
            "description": "PA speaker",
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == EQUIPMENT_ID
    assert fake_client.rpc_calls == [
        (
            "create_equipment",
            {
                "p_type": "Speaker",
                "p_description": "PA speaker",
                "p_total_owned_quantity": 4,
                "p_home_location": "Store Room B",
                "p_operational_status": "AVAILABLE",
                "p_created_by": USER_ID,
            },
        )
    ]


def test_create_equipment_negative_quantity(
    client: TestClient, auth_staff
) -> None:
    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "Speaker",
            "total_owned_quantity": -1,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 422


def test_create_equipment_missing_required_fields(
    client: TestClient, auth_staff
) -> None:
    response = client.post(
        "/equipment",
        headers=bearer(),
        json={"type": "Speaker"},
    )

    assert response.status_code == 422


def test_create_equipment_type_too_long(client: TestClient, auth_staff) -> None:
    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "S" * 121,
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 422


def test_create_equipment_home_location_too_long(
    client: TestClient, auth_staff
) -> None:
    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "Speaker",
            "total_owned_quantity": 4,
            "home_location": "S" * 121,
        },
    )

    assert response.status_code == 422


def test_create_equipment_with_explicit_status(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_result = {
        **EQUIPMENT_ROW,
        "operational_status": "DAMAGED",
    }

    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "Speaker",
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
            "operational_status": "DAMAGED",
        },
    )

    assert response.status_code == 201
    assert response.json()["operational_status"] == "DAMAGED"
    assert fake_client.rpc_calls[0][1]["p_operational_status"] == "DAMAGED"


def test_create_equipment_description_optional(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_result = {**EQUIPMENT_ROW, "description": None}

    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "Speaker",
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 201
    assert response.json()["description"] is None
    assert fake_client.rpc_calls[0][1]["p_description"] is None


def test_update_quantity_requires_authentication(client: TestClient) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 401


def test_update_quantity_forbidden_for_event_coordinator(
    client: TestClient, auth
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 403


def test_update_quantity(client: TestClient, fake_client, auth_staff) -> None:
    fake_client.rpc_result = {**EQUIPMENT_ROW, "total_owned_quantity": 6}

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 200
    assert response.json()["total_owned_quantity"] == 6
    assert fake_client.rpc_calls == [
        (
            "update_equipment_quantity",
            {
                "p_equipment_id": EQUIPMENT_ID,
                "p_new_quantity": 6,
                "p_changed_by": USER_ID,
            },
        )
    ]


def test_update_quantity_negative(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": -3},
    )

    assert response.status_code == 422
    assert fake_client.rpc_calls == []


def test_update_quantity_zero(client: TestClient, fake_client, auth_staff) -> None:
    fake_client.rpc_result = {**EQUIPMENT_ROW, "total_owned_quantity": 0}

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": 0},
    )

    assert response.status_code == 200
    assert response.json()["total_owned_quantity"] == 0


def test_update_quantity_not_found(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_error = APIError(
        {"message": "row not found", "code": "P0002"}
    )

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Equipment not found"


def test_update_quantity_rpc_failure(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_error = APIError(
        {"message": "equipment not found", "code": "P0001"}
    )

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 500
