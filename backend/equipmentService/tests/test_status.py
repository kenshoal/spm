from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.clock import get_today
from app.main import app

USER_ID = "11111111-1111-1111-1111-111111111111"
EQUIPMENT_ID = "22222222-2222-2222-2222-222222222222"

EQUIPMENT_ROW: dict[str, Any] = {
    "id": EQUIPMENT_ID,
    "operational_status": "AVAILABLE",
    "total_owned_quantity": 4,
}


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


# AC2-X1 (cross-cutting): the availability lookup requires an authenticated session
def test_get_status_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}/status")

    assert response.status_code == 401


# AC2-X2 (cross-cutting): every malformed Authorization header variant is refused
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


# AC2-H1 (happy path): available equipment reports available=true with its quantity
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
        "available_quantity": 4,
    }


# AC2-B1 (boundary): zero owned quantity is the availability floor — still available, quantity 0
def test_get_status_available_zero_owned(
    client: TestClient, fake_client, auth
) -> None:
    fake_client.table_data["equipment"] = [{**EQUIPMENT_ROW, "total_owned_quantity": 0}]

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status", headers=bearer()
    )

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["available_quantity"] == 0


# AC2-P1 (partition): DAMAGED equipment is excluded from availability
def test_get_status_unavailable(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [
        {**EQUIPMENT_ROW, "operational_status": "DAMAGED"}
    ]

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status", headers=bearer()
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["available_quantity"] == 0


# AC2-P2, AC2-P3, AC2-P4 (partition): every other non-AVAILABLE status is also excluded
@pytest.mark.parametrize(
    "row_status",
    ["UNDER_REPAIR", "UNDER_MAINTENANCE", "RETIRED"],
    ids=["AC2-P2", "AC2-P3", "AC2-P4"],
)
def test_get_status_excludes_all_unavailable_statuses(
    client: TestClient, fake_client, auth, row_status: str
) -> None:
    fake_client.table_data["equipment"] = [
        {**EQUIPMENT_ROW, "operational_status": row_status}
    ]

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status", headers=bearer()
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["available_quantity"] == 0
    assert response.json()["operational_status"] == row_status


# AC2-N1 (negative): an unknown equipment id is 404, not an empty 200
def test_get_status_not_found(client: TestClient, fake_client, auth) -> None:
    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status", headers=bearer()
    )

    assert response.status_code == 404


# AC4-N3 (negative): Attendees cannot read equipment status or its history (403)
@pytest.mark.parametrize(
    "suffix", ["status", "status/history"]
)
def test_equipment_status_reads_forbidden_for_attendees(
    client: TestClient, auth_attendee, suffix: str
) -> None:
    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/{suffix}", headers=bearer()
    )

    assert response.status_code == 403


# AC2-N2 (negative): a malformed equipment id is refused before any query runs
def test_get_status_invalid_equipment_id(client: TestClient, auth) -> None:
    response = client.get("/equipment/not-a-uuid/status", headers=bearer())

    assert response.status_code == 422


# AC1-X1 (cross-cutting): transitioning requires an authenticated session; no status write happens
def test_transition_status_requires_authentication(
    client: TestClient, fake_client
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 401
    assert fake_client.rpc_calls == []


# AC1-X2 (cross-cutting): an event coordinator may not transition status; no status write happens
def test_transition_status_forbidden_for_event_coordinator(
    client: TestClient, fake_client, auth
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "DAMAGED"},
    )

    assert response.status_code == 403
    assert fake_client.rpc_calls == []


# AC1-H1 (happy path): technical support marks equipment DAMAGED with a reason
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


# AC1-P1 (partition): the reason is optional
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


# AC1-P2 (partition): UNDER_MAINTENANCE is an accepted target status
def test_transition_status_under_maintenance(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "UNDER_MAINTENANCE"},
    )

    assert response.status_code == 200
    assert response.json()["new_status"] == "UNDER_MAINTENANCE"
    assert fake_client.rpc_calls[0][1]["p_new_status"] == "UNDER_MAINTENANCE"


# AC1-P3 (partition): RETIRED is an accepted target status (see scrum_16 open question on transition legality)
def test_transition_status_retired(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "RETIRED"},
    )

    assert response.status_code == 200
    assert response.json()["new_status"] == "RETIRED"
    assert fake_client.rpc_calls[0][1]["p_new_status"] == "RETIRED"


# AC1-P4 (partition): repaired equipment can be returned to AVAILABLE (user story: "update the operational status")
def test_transition_status_back_to_available(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "AVAILABLE", "reason": "Repair completed"},
    )

    assert response.status_code == 200
    assert response.json()["new_status"] == "AVAILABLE"
    assert fake_client.rpc_calls == [
        (
            "transition_equipment_status",
            {
                "p_equipment_id": EQUIPMENT_ID,
                "p_new_status": "AVAILABLE",
                "p_changed_by": USER_ID,
                "p_reason": "Repair completed",
            },
        )
    ]


# AC1-B1 (boundary): a reason of exactly 255 characters is accepted
def test_transition_status_reason_at_max_length(
    client: TestClient, fake_client, auth_staff
) -> None:
    reason = "x" * 255

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "DAMAGED", "reason": reason},
    )

    assert response.status_code == 200
    assert fake_client.rpc_calls[0][1]["p_reason"] == reason


# AC1-B2 (boundary): a reason of 256 characters is refused and nothing is written
def test_transition_status_reason_too_long(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "DAMAGED", "reason": "x" * 256},
    )

    assert response.status_code == 422
    assert fake_client.rpc_calls == []


# AC1-N1 (negative): an unknown status value is rejected by validation; no status write happens
def test_transition_status_invalid_status(
    client: TestClient, fake_client, auth_staff
) -> None:
    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "ON_FIRE"},
    )

    assert response.status_code == 422
    assert fake_client.rpc_calls == []


# AC1-N2 (negative): a malformed equipment id is refused before the RPC runs
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


# AC1-N3 (negative): an unknown equipment maps RPC errcode P0002 to 404
def test_transition_status_unknown_equipment(
    client: TestClient, fake_client, auth_staff
) -> None:
    fake_client.rpc_error = APIError(
        {"message": "no rows", "code": "P0002"}
    )

    response = client.patch(
        f"/equipment/{EQUIPMENT_ID}/status",
        headers=bearer(),
        json={"new_status": "RETIRED"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Equipment not found"


# AC1-N4 (negative): regression — 404 keys off errcode P0002, not error-message text
def test_transition_status_other_error_with_not_found_message(
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

    assert response.status_code == 500


# AC1-N5 (negative): a generic RPC failure is a 500, not a crash
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


# AC3-X1 (cross-cutting): the history read requires an authenticated session
def test_status_history_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/equipment/{EQUIPMENT_ID}/status/history")

    assert response.status_code == 401


# AC3-H1 (happy path): history lists each change with who and when, newest first
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


# AC3-N1 (negative): the history of an unknown equipment is 404
def test_status_history_unknown_equipment(
    client: TestClient, fake_client, auth
) -> None:
    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status/history", headers=bearer()
    )

    assert response.status_code == 404


# AC3-P1 (partition): equipment with no status changes yet returns an empty history (200 [])
def test_status_history_empty(client: TestClient, fake_client, auth) -> None:
    fake_client.table_data["equipment"] = [EQUIPMENT_ROW]
    fake_client.table_data["equipment_status_history"] = []

    response = client.get(
        f"/equipment/{EQUIPMENT_ID}/status/history", headers=bearer()
    )

    assert response.status_code == 200
    assert response.json() == []


# --- SCRUM-10: GET /status subtracts units reserved today ---------------------
# Test-case IDs trace to docs/testcases/scrum_10_testcases.md (AC3).

MON12 = date(2026, 10, 12)


@pytest.fixture
def frozen_today():
    # The client fixture clears dependency overrides on teardown.
    app.dependency_overrides[get_today] = lambda: MON12
    yield MON12


def reserved(qty: int, collect: str, ret: str) -> dict[str, Any]:
    return {
        "equipment_id": EQUIPMENT_ID,
        "quantity": qty,
        "collection_date": collect,
        "return_date": ret,
    }


def seed_status(fake_client, *, qty: int, status: str, reservations: list) -> None:
    fake_client.table_data["equipment"] = [
        {**EQUIPMENT_ROW, "total_owned_quantity": qty, "operational_status": status}
    ]
    fake_client.table_data["equipment_reservations"] = reservations


# AC3-H3 (happy): GET /status subtracts the units reserved today
def test_get_status_subtracts_units_reserved_today(
    client: TestClient, fake_client, auth, frozen_today
) -> None:
    seed_status(
        fake_client,
        qty=10,
        status="AVAILABLE",
        reservations=[reserved(4, "2026-10-11", "2026-10-13")],
    )

    response = client.get(f"/equipment/{EQUIPMENT_ID}/status", headers=bearer())

    assert response.status_code == 200
    assert response.json() == {
        "equipment_id": EQUIPMENT_ID,
        "operational_status": "AVAILABLE",
        "available": True,
        "available_quantity": 6,
    }
    assert fake_client.inserts == [] and fake_client.updates == []


# AC3-B3, AC3-B4, AC3-B5, AC3-B6 (boundary): only reservations covering today count
@pytest.mark.parametrize(
    ("collect", "ret", "available_quantity"),
    [
        ("2026-10-10", "2026-10-11", 10),  # returned yesterday
        ("2026-10-11", "2026-10-12", 6),  # returning today
        ("2026-10-12", "2026-10-13", 6),  # collecting today
        ("2026-10-13", "2026-10-14", 10),  # collecting tomorrow
    ],
    ids=["AC3-B3", "AC3-B4", "AC3-B5", "AC3-B6"],
)
def test_get_status_counts_only_reservations_covering_today(
    client: TestClient,
    fake_client,
    auth,
    frozen_today,
    collect: str,
    ret: str,
    available_quantity: int,
) -> None:
    seed_status(
        fake_client, qty=10, status="AVAILABLE", reservations=[reserved(4, collect, ret)]
    )

    response = client.get(f"/equipment/{EQUIPMENT_ID}/status", headers=bearer())

    assert response.status_code == 200
    assert response.json()["available_quantity"] == available_quantity


# AC3-P6 (partition): fully reserved working stock stays available=true (proposal 6)
def test_get_status_fully_reserved_stays_available(
    client: TestClient, fake_client, auth, frozen_today
) -> None:
    seed_status(
        fake_client,
        qty=10,
        status="AVAILABLE",
        reservations=[reserved(10, "2026-10-11", "2026-10-12")],
    )

    response = client.get(f"/equipment/{EQUIPMENT_ID}/status", headers=bearer())

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["available_quantity"] == 0


# AC3-P7 (partition): a non-AVAILABLE row with a reservation stays at 0, never negative
def test_get_status_unavailable_row_with_reservation_is_zero(
    client: TestClient, fake_client, auth, frozen_today
) -> None:
    seed_status(
        fake_client,
        qty=10,
        status="DAMAGED",
        reservations=[reserved(4, "2026-10-11", "2026-10-12")],
    )

    response = client.get(f"/equipment/{EQUIPMENT_ID}/status", headers=bearer())

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["available_quantity"] == 0
