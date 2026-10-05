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


# Cross-cutting (smoke, DoD-level; outside the AC matrix): the service answers at /
def test_hello(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "equipmentService",
        "message": "Hello from equipmentService",
    }


# Cross-cutting (smoke, DoD-level; outside the AC matrix): the health check reports ok
def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "equipmentService",
        "status": "ok",
    }


# AC3-X1 (cross-cutting): listing the catalogue requires an authenticated session
def test_list_equipment_requires_authentication(client: TestClient) -> None:
    response = client.get("/equipment")

    assert response.status_code == 401


# AC3-X2 (cross-cutting): every malformed Authorization header variant is refused
@pytest.mark.parametrize(
    "authorization", ["Basic abc", "Bearer ", "Bearer a b", "Bearer"]
)
def test_list_equipment_rejects_malformed_bearer(
    client: TestClient, authorization: str
) -> None:
    response = client.get("/equipment", headers={"Authorization": authorization})

    assert response.status_code == 401


# AC3-H1 (happy path): the catalogue lists records with their current attributes
def test_list_equipment(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get("/equipment", headers=bearer())

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == EQUIPMENT_ID
    assert body[0]["operational_status"] == "AVAILABLE"


# AC3-P1 (partition): the list can be filtered by type and operational status
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


# AC3-N1 (negative): an empty catalogue is presented as 200 [] for a valid query
def test_list_equipment_empty(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = []

    response = client.get("/equipment", headers=bearer())

    assert response.status_code == 200
    assert response.json() == []


# AC3-N2 (negative): an unknown operational_status filter value is refused
def test_list_equipment_invalid_status_filter(
    client: TestClient, auth
) -> None:
    response = client.get(
        "/equipment", headers=bearer(), params={"operational_status": "BOGUS"}
    )

    assert response.status_code == 422


# AC3-H2 (happy path): a single record shows its current attributes
def test_get_equipment(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]

    response = client.get(f"/equipment/{EQUIPMENT_ID}", headers=bearer())

    assert response.status_code == 200
    assert response.json()["id"] == EQUIPMENT_ID


# AC3-N3 (negative): an unknown equipment id is 404
def test_get_equipment_not_found(client: TestClient, auth) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}", headers=bearer())

    assert response.status_code == 404


# AC3-N4 (negative): a malformed equipment id is refused
def test_get_equipment_invalid_id(client: TestClient, auth) -> None:
    response = client.get("/equipment/not-a-uuid", headers=bearer())

    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/equipment", f"/equipment/{EQUIPMENT_ID}"])
def test_equipment_reads_forbidden_for_attendees(
    client: TestClient, auth_attendee, path: str
) -> None:
    response = client.get(path, headers=bearer())

    assert response.status_code == 403


# AC1-X1 (cross-cutting): creating requires an authenticated session
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


# AC1-X2 (cross-cutting): an event coordinator may not create equipment
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


# AC1-H1 (happy path): technical support creates a record with every attribute
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


# AC1-P1 (partition): a matching role anywhere in the roles list is sufficient
def test_create_equipment_allows_matching_role_in_roles_list(
    client: TestClient, fake_client, auth_manager_staff
) -> None:
    fake_client.rpc_result = dict(EQUIPMENT_ROW)

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


# AC1-N1 (negative): a negative total owned quantity is refused
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


# AC1-N2 (negative): missing required fields are refused
def test_create_equipment_missing_required_fields(
    client: TestClient, auth_staff
) -> None:
    response = client.post(
        "/equipment",
        headers=bearer(),
        json={"type": "Speaker"},
    )

    assert response.status_code == 422


# AC1-B1 (boundary): a type of exactly 120 characters is accepted
def test_create_equipment_type_at_max_length(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_result = dict(EQUIPMENT_ROW)

    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "S" * 120,
            "total_owned_quantity": 4,
            "home_location": "Store Room B",
        },
    )

    assert response.status_code == 201
    assert fake_client.rpc_calls[0][1]["p_type"] == "S" * 120


# AC1-B2 (boundary): a type of 121 characters is refused
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


# AC1-B3 (boundary): a home location of exactly 120 characters is accepted
def test_create_equipment_home_location_at_max_length(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_result = dict(EQUIPMENT_ROW)

    response = client.post(
        "/equipment",
        headers=bearer(),
        json={
            "type": "Speaker",
            "total_owned_quantity": 4,
            "home_location": "S" * 120,
        },
    )

    assert response.status_code == 201
    assert fake_client.rpc_calls[0][1]["p_home_location"] == "S" * 120


# AC1-B4 (boundary): a home location of 121 characters is refused
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


# AC1-P2 (partition): an explicit non-default operational status is honoured
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


# AC1-P3 (partition): the description is optional and defaults to null
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


# AC2-X1 (cross-cutting): updating quantity requires an authenticated session
def test_update_quantity_requires_authentication(client: TestClient) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 401


# AC2-X2 (cross-cutting): an event coordinator may not update quantity
def test_update_quantity_forbidden_for_event_coordinator(
    client: TestClient, auth
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": 6},
    )

    assert response.status_code == 403


# AC2-H1 (happy path): technical support updates the total owned quantity
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


# AC2-N1 (negative): a negative quantity is refused and nothing is written
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


# AC2-B1 (boundary): zero is the accepted quantity floor
def test_update_quantity_zero(client: TestClient, fake_client, auth_staff) -> None:
    fake_client.rpc_result = {**EQUIPMENT_ROW, "total_owned_quantity": 0}

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/quantity",
        headers=bearer(),
        json={"total_owned_quantity": 0},
    )

    assert response.status_code == 200
    assert response.json()["total_owned_quantity"] == 0


# AC2-N2 (negative): an unknown equipment maps RPC errcode P0002 to 404
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


# AC2-N3 (negative): a generic RPC failure is a 500, not a crash
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
