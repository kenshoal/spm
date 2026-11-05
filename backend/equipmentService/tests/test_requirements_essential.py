"""Hotfix 25 (Q&A #80, #106): the Coordinator marks an equipment requirement not essential.

PATCH /equipment-requirements/{id}/essential. The rule that a not-essential requirement does
not block confirmation lives in the database (verified by
database/verify_release_1_hotfixes.sql, AC25); these cases prove the API contract and its
error mapping.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from requirements_support import (
    C1,
    C2,
    FakeEventService,
    RequirementsStore,
    api_error,
    bearer,
    requirement_row,
)

ROW = requirement_row()
SAVED = {
    **ROW,
    "essential": False,
    "essential_note": "Support will bring one on the day",
}
URL = f"/equipment-requirements/{ROW['id']}/essential"
BODY = {"essential": False, "note": "Support will bring one on the day"}


@pytest.fixture
def coordinator(as_user, req_store: RequirementsStore) -> None:
    as_user("event_coordinator", user_id=C1)
    req_store.rows["equipment_requirements"] = [dict(ROW)]
    req_store.rpc_result = dict(SAVED)


# AC25-H1 (happy): the assigned Coordinator marks a requirement not essential, with a note
def test_coordinator_marks_a_requirement_not_essential(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    response = req_api.patch(URL, json=BODY, headers=bearer())

    assert response.status_code == 200, response.text
    assert response.json()["essential"] is False
    assert response.json()["essential_note"] == "Support will bring one on the day"
    assert req_store.rpc_calls == [(
        "set_requirement_essential",
        {"p_requirement_id": ROW["id"], "p_coordinator_id": C1, "p_essential": False,
         "p_note": "Support will bring one on the day"},
    )]


# AC25-H2 (happy): marking it essential again needs no note
def test_coordinator_marks_it_essential_again(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    req_store.rpc_result = dict(ROW)

    response = req_api.patch(URL, json={"essential": True}, headers=bearer())

    assert response.status_code == 200, response.text
    assert response.json()["essential"] is True
    assert req_store.rpc_calls[0][1]["p_note"] is None


# AC25-H3 (happy): an unchanged row reads as essential, as before the change
def test_existing_rows_read_as_essential() -> None:
    from app.routers.requirements import RequirementOut

    assert RequirementOut.model_validate(requirement_row()).essential is True


# AC25-N1 (negative): not essential without a note, or with a blank one, is refused before the database
@pytest.mark.parametrize("body", [{"essential": False}, {"essential": False, "note": "   "}],
                         ids=["AC25-N1a", "AC25-N1b"])
def test_not_essential_needs_a_note(
    req_api: TestClient, req_store: RequirementsStore, coordinator, body: dict[str, Any]
) -> None:
    response = req_api.patch(URL, json=body, headers=bearer())

    assert response.status_code == 422
    assert req_store.rpc_calls == []


# AC25-N2 (negative): only a Coordinator may mark a requirement; Technical Support may not
def test_technical_support_cannot_mark_a_requirement(
    req_api: TestClient, req_store: RequirementsStore, as_user
) -> None:
    as_user("technical_support")
    req_store.rows["equipment_requirements"] = [dict(ROW)]

    response = req_api.patch(URL, json=BODY, headers=bearer())

    assert response.status_code == 403
    assert req_store.rpc_calls == []


# AC25-N3 (negative): a Coordinator who is not assigned to the event sees "not found"
def test_unassigned_coordinator_gets_not_found(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_coordinator", user_id=C2)
    req_store.rows["equipment_requirements"] = [dict(ROW)]

    response = req_api.patch(URL, json=BODY, headers=bearer())

    assert response.status_code == 404
    assert req_store.rpc_calls == []


# AC25-N4 (negative): an unknown requirement is not found
def test_unknown_requirement_is_not_found(
    req_api: TestClient, req_store: RequirementsStore, as_user
) -> None:
    as_user("event_coordinator", user_id=C1)

    response = req_api.patch(URL, json=BODY, headers=bearer())

    assert response.status_code == 404
    assert req_store.rpc_calls == []


# AC25-N5 (negative): each database refusal becomes its own status
@pytest.mark.parametrize(
    ("code", "status_code"),
    [("P0002", 404), ("P0003", 404), ("P0004", 409), ("22023", 422), ("XX000", 500)],
    ids=["AC25-N5a", "AC25-N5b", "AC25-N5c", "AC25-N5d", "AC25-N5e"],
)
def test_database_refusals_map_to_statuses(
    req_api: TestClient, req_store: RequirementsStore, coordinator, code: str, status_code: int
) -> None:
    req_store.rpc_error = api_error(code)

    response = req_api.patch(URL, json=BODY, headers=bearer())

    assert response.status_code == status_code


# AC25-B1 (boundary): a note of 2000 characters is accepted and 2001 is refused
@pytest.mark.parametrize(("length", "status_code"), [(2000, 200), (2001, 422)],
                         ids=["AC25-B1a", "AC25-B1b"])
def test_note_length_boundary(
    req_api: TestClient, req_store: RequirementsStore, coordinator, length: int, status_code: int
) -> None:
    response = req_api.patch(
        URL, json={"essential": False, "note": "n" * length}, headers=bearer())

    assert response.status_code == status_code


# AC25-X1 (cross-cutting): a withdrawn or postponed event refuses new requirements
@pytest.mark.parametrize("event_status", ["Withdrawn", "Postponed"], ids=["AC25-X1a", "AC25-X1b"])
def test_withdrawn_and_postponed_events_are_closed(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService,
    as_user, event_status: str
) -> None:
    as_user("event_coordinator", user_id=C1)
    req_events.event["status"] = event_status

    response = req_api.post(
        "/equipment-requirements",
        json={"event_request_id": req_events.event["id"], "equipment_type": "Projector",
              "quantity": 1},
        headers=bearer(),
    )

    assert response.status_code == 409
    assert req_store.inserts == []
