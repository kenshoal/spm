"""Arrangement-update tests for "Record Equipment Requirements for an Event" (SCRUM-33).

PATCH /equipment-requirements/{id}/arrangement. The transition table lives
in the database function transition_equipment_requirement (covered by
database/verify_equipment_requirements.sql); these cases prove the API
contract and its error mapping. Every test carries its case ID from
docs/testcases/scrum_33_testcases.md.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from requirements_support import (
    C1,
    TSS,
    FakeEventService,
    RequirementsStore,
    api_error,
    bearer,
    requirement_row,
)

ROW = requirement_row(recorded_at="2026-10-06T09:00:00+08:00")
UPDATED = {
    **ROW,
    "status": "in_progress",
    "support_note": "Sourcing spare",
    "updated_by": TSS,
    "updated_at": "2026-10-06T11:00:00+08:00",
}
URL = f"/equipment-requirements/{ROW['id']}/arrangement"


def change(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "expected_status": "requested",
        "status": "in_progress",
        "support_note": "Sourcing spare",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def staff(as_user) -> None:
    as_user("technical_support", user_id=TSS)


# AC5-H2 (happy): Technical Support moves a requirement to in progress, recorded as them
def test_technical_support_updates_arrangement(
    req_api: TestClient, req_store: RequirementsStore, staff
) -> None:
    req_store.rpc_result = dict(UPDATED)

    response = req_api.patch(URL, json=change(), headers=bearer())

    assert response.status_code == 200
    assert response.json() == UPDATED
    assert req_store.rpc_calls == [
        (
            "transition_equipment_requirement",
            {
                "p_requirement_id": ROW["id"],
                "p_expected_status": "requested",
                "p_new_status": "in_progress",
                "p_support_note": "Sourcing spare",
                "p_updated_by": TSS,
            },
        )
    ]
    assert req_store.inserts == []


# AC5-P8 (partition): a user holding Technical Support among other roles can update
def test_multi_role_staff_can_update(
    req_api: TestClient, req_store: RequirementsStore, as_user
) -> None:
    as_user("event_operations_manager", "technical_support", user_id=TSS)
    req_store.rpc_result = dict(UPDATED)

    response = req_api.patch(URL, json=change(), headers=bearer())

    assert response.status_code == 200


# AC5-X3 (cross-cutting): the assigned Coordinator sees the arrangement status, note, who and when
def test_coordinator_sees_the_update(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    req_store.rows["equipment_requirements"] = [dict(UPDATED)]
    as_user("event_coordinator", user_id=C1)

    response = req_api.get(f"/equipment-requirements/{ROW['id']}", headers=bearer())

    assert response.status_code == 200
    data = response.json()
    assert (data["status"], data["support_note"], data["updated_by"], data["updated_at"]) == (
        "in_progress",
        "Sourcing spare",
        TSS,
        "2026-10-06T11:00:00+08:00",
    )


# AC5-N11 (negative): a disallowed or stale transition from the database is a 409
def test_refused_transition_is_conflict(
    req_api: TestClient, req_store: RequirementsStore, staff
) -> None:
    req_store.rpc_error = api_error("P0004")

    response = req_api.patch(URL, json=change(), headers=bearer())

    assert response.status_code == 409
    assert response.json() == {"detail": "Transition not allowed"}


# AC5-N12 (negative): an unknown requirement is not found
def test_unknown_requirement_is_not_found(
    req_api: TestClient, req_store: RequirementsStore, staff
) -> None:
    req_store.rpc_error = api_error("P0002")

    response = req_api.patch(URL, json=change(), headers=bearer())

    assert response.status_code == 404
    assert response.json() == {"detail": "Equipment requirement not found"}


# AC5-N13 (negative): any other database error is a 500
def test_other_database_error_is_server_error(
    req_api: TestClient, req_store: RequirementsStore, staff
) -> None:
    req_store.rpc_error = api_error("XX000")

    response = req_api.patch(URL, json=change(), headers=bearer())

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed"}


# AC5-N14 to AC5-N16 (negative): an unknown status, a missing expected status or an over-long note never reaches the database
@pytest.mark.parametrize(
    "payload",
    [
        change(status="done"),
        {k: v for k, v in change().items() if k != "expected_status"},
        change(support_note="x" * 2001),
    ],
    ids=["AC5-N14", "AC5-N15", "AC5-N16"],
)
def test_invalid_update_is_refused(
    req_api: TestClient, req_store: RequirementsStore, staff, payload: dict[str, Any]
) -> None:
    response = req_api.patch(URL, json=payload, headers=bearer())

    assert response.status_code == 422
    assert req_store.rpc_calls == []


# AC5-N17 to AC5-N19 (negative): Coordinator-owned and server-owned fields cannot be changed here
@pytest.mark.parametrize(
    "extra",
    [{"quantity": 5}, {"equipment_type": "Speaker"}, {"updated_by": C1}],
    ids=["AC5-N17", "AC5-N18", "AC5-N19"],
)
def test_other_fields_are_forbidden(
    req_api: TestClient, req_store: RequirementsStore, staff, extra: dict[str, Any]
) -> None:
    response = req_api.patch(URL, json={**change(), **extra}, headers=bearer())

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
    assert req_store.rpc_calls == []


# AC6-X23, AC6-X24 (cross-cutting): only Technical Support may update, not even the assigned Coordinator
@pytest.mark.parametrize(
    "role", ["event_coordinator", "event_organiser"], ids=["AC6-X23", "AC6-X24"]
)
def test_only_technical_support_updates(
    req_api: TestClient, req_store: RequirementsStore, as_user, role: str
) -> None:
    as_user(role, user_id=C1)

    response = req_api.patch(URL, json=change(), headers=bearer())

    assert response.status_code == 403
    assert req_store.rpc_calls == []


# AC6-X25 (cross-cutting): an update needs a bearer token
def test_update_requires_authentication(
    req_api: TestClient, req_store: RequirementsStore, staff
) -> None:
    response = req_api.patch(URL, json=change())

    assert response.status_code == 401
    assert req_store.rpc_calls == []
