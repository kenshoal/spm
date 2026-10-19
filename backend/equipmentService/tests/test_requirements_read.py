"""Read and queue tests for "Record Equipment Requirements for an Event" (SCRUM-33).

GET /equipment-requirements/by-event/{event_request_id}, GET
/equipment-requirements/{id} and the Technical Support queue
GET /equipment-requirements. Every test carries its case ID from
docs/testcases/scrum_33_testcases.md.
"""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from requirements_support import (
    C1,
    C2,
    E1,
    E2,
    MISSING,
    TSS,
    FakeEventService,
    RequirementsStore,
    bearer,
    requirement_row,
)

QUEUE = "/equipment-requirements"

# Stored deliberately out of order so a missing ORDER BY is caught.
ROW_A = requirement_row(recorded_at="2026-10-06T09:00:00+08:00")
ROW_B = requirement_row(
    equipment_type="Wireless Microphone",
    quantity=4,
    technical_requirements=None,
    status="in_progress",
    support_note="Sourcing spare",
    recorded_at="2026-10-06T10:00:00+08:00",
    updated_by=TSS,
    updated_at="2026-10-06T11:00:00+08:00",
)
ROW_C = requirement_row(
    event_request_id=E2, event_name="Board Retreat", recorded_by=C2,
    recorded_at="2026-10-06T08:00:00+08:00",
)
ROW_D = requirement_row(
    event_request_id=E2, event_name="Board Retreat", recorded_by=C2,
    status="arranged", updated_by=TSS, updated_at="2026-10-06T12:00:00+08:00",
    recorded_at="2026-10-06T07:00:00+08:00",
)


def by_event(event_id: str = E1) -> str:
    return f"/equipment-requirements/by-event/{event_id}"


def one(requirement_id: str) -> str:
    return f"/equipment-requirements/{requirement_id}"


def ids(response: httpx.Response) -> list[str]:
    return [item["id"] for item in response.json()]


@pytest.fixture
def seeded(req_store: RequirementsStore) -> RequirementsStore:
    req_store.rows["equipment_requirements"] = [
        dict(r) for r in (ROW_B, ROW_D, ROW_A, ROW_C)
    ]
    return req_store


def expected(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


# AC3-H1 (happy): the assigned Coordinator lists the event's requirements, oldest first, with every field
def test_coordinator_lists_event_requirements(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_coordinator", user_id=C1)

    response = req_api.get(by_event(), headers=bearer())

    assert response.status_code == 200
    assert response.json() == [expected(ROW_A), expected(ROW_B)]
    assert req_events.paths() == [f"/event-requests/{E1}/coordinator"]


# AC3-H2 (happy): Technical Support lists the same without asking eventRequestService
def test_technical_support_lists_event_requirements(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(by_event(), headers=bearer())

    assert response.status_code == 200
    assert ids(response) == [ROW_A["id"], ROW_B["id"]]
    assert req_events.requests == []


# AC3-H3 (happy): the assigned Coordinator opens one requirement and sees every field
def test_coordinator_opens_one_requirement(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_coordinator", user_id=C1)

    response = req_api.get(one(ROW_B["id"]), headers=bearer())

    assert response.status_code == 200
    assert response.json() == expected(ROW_B)
    assert req_events.paths() == [f"/event-requests/{E1}/coordinator"]


# AC3-H4 (happy): Technical Support opens any requirement without asking eventRequestService
def test_technical_support_opens_one_requirement(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(one(ROW_C["id"]), headers=bearer())

    assert response.status_code == 200
    assert response.json() == expected(ROW_C)
    assert req_events.requests == []


# AC3-B1 (boundary): an event with no requirements returns an empty list
def test_event_without_requirements_is_empty(
    req_api: TestClient, req_store: RequirementsStore, as_user
) -> None:
    as_user("event_coordinator", user_id=C1)

    response = req_api.get(by_event(), headers=bearer())

    assert response.status_code == 200
    assert response.json() == []


# AC3-X1 (cross-cutting): the snapshot comes from the stored row, not a fresh read of the event
def test_snapshot_is_not_refreshed_from_the_event(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_coordinator", user_id=C1)
    req_events.event["event_name"] = "Gala 2027"

    response = req_api.get(by_event(), headers=bearer())

    assert response.status_code == 200
    assert [item["event_name"] for item in response.json()] == ["Annual Gala"] * 2
    assert f"/event-requests/{E1}" not in req_events.paths()


# AC3-N1 (negative): an unknown requirement is not found
def test_unknown_requirement_is_not_found(
    req_api: TestClient, seeded: RequirementsStore, as_user
) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(one(MISSING), headers=bearer())

    assert response.status_code == 404
    assert response.json() == {"detail": "Equipment requirement not found"}


# AC3-N2 (negative): a malformed id is refused without querying the store
def test_malformed_id_is_refused(
    req_api: TestClient, seeded: RequirementsStore, as_user
) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(one("not-a-uuid"), headers=bearer())

    assert response.status_code == 422
    assert seeded.requirement_queries() == []


# AC4-H1 (happy): the default queue shows only requested requirements from every event, oldest first
def test_default_queue_is_requested_oldest_first(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(QUEUE, headers=bearer())

    assert response.status_code == 200
    assert ids(response) == [ROW_C["id"], ROW_A["id"]]
    assert [(i["event_request_id"], i["event_name"]) for i in response.json()] == [
        (E2, "Board Retreat"),
        (E1, "Annual Gala"),
    ]
    assert req_events.requests == []


# AC4-P1, AC4-P2 (partition): the status filter selects in-progress or arranged requirements
@pytest.mark.parametrize(
    ("status", "row"),
    [("in_progress", ROW_B), ("arranged", ROW_D)],
    ids=["AC4-P1", "AC4-P2"],
)
def test_queue_status_filter(
    req_api: TestClient, seeded: RequirementsStore, as_user, status: str, row: dict[str, Any]
) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(QUEUE, params={"status": status}, headers=bearer())

    assert response.status_code == 200
    assert ids(response) == [row["id"]]


# AC4-B1 (boundary): an empty queue returns an empty list
def test_empty_queue(req_api: TestClient, req_store: RequirementsStore, as_user) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(QUEUE, headers=bearer())

    assert response.status_code == 200
    assert response.json() == []


# AC4-N1 (negative): an unknown status filter is refused without querying the store
def test_unknown_queue_status_is_refused(
    req_api: TestClient, seeded: RequirementsStore, as_user
) -> None:
    as_user("technical_support", user_id=TSS)

    response = req_api.get(QUEUE, params={"status": "cancelled"}, headers=bearer())

    assert response.status_code == 422
    assert seeded.requirement_queries() == []


# AC6-X17, AC6-X18 (cross-cutting): Coordinators and organisers cannot read the review queue
@pytest.mark.parametrize(
    "role", ["event_coordinator", "event_organiser"], ids=["AC6-X17", "AC6-X18"]
)
def test_queue_is_technical_support_only(
    req_api: TestClient, seeded: RequirementsStore, as_user, role: str
) -> None:
    as_user(role, user_id=C1)

    response = req_api.get(QUEUE, headers=bearer())

    assert response.status_code == 403
    assert seeded.requirement_queries() == []


# AC6-X19 (cross-cutting): an unassigned Coordinator gets the same 404s as for things that do not exist
def test_unassigned_coordinator_cannot_list_or_open(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_coordinator", user_id=C1)
    req_events.coordinator_id = C2

    listed = req_api.get(by_event(), headers=bearer())
    opened = req_api.get(one(ROW_A["id"]), headers=bearer())
    unknown = req_api.get(one(MISSING), headers=bearer())

    assert listed.status_code == 404
    assert listed.json() == {"detail": "Event request not found"}
    assert opened.status_code == 404
    assert opened.json() == unknown.json() == {"detail": "Equipment requirement not found"}


# AC6-X20 (cross-cutting): after reassignment the former Coordinator loses access and the new one gains it
def test_reassignment_moves_access(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    req_events.coordinator_id = C2

    as_user("event_coordinator", user_id=C1)
    former = req_api.get(one(ROW_A["id"]), headers=bearer())
    as_user("event_coordinator", user_id=C2)
    current = req_api.get(one(ROW_A["id"]), headers=bearer())

    assert former.status_code == 404
    assert current.status_code == 200
    assert current.json()["recorded_by"] == C1


# AC6-X21 (cross-cutting): the organiser who owns the event cannot read its equipment requirements
def test_owning_organiser_cannot_read(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_organiser", user_id=req_events.event["organiser_id"])

    listed = req_api.get(by_event(), headers=bearer())
    opened = req_api.get(one(ROW_A["id"]), headers=bearer())

    assert listed.status_code == opened.status_code == 403
    assert req_events.requests == []


# AC6-X22 (cross-cutting): every read needs a bearer token
def test_reads_require_authentication(
    req_api: TestClient, seeded: RequirementsStore, as_user
) -> None:
    as_user("technical_support", user_id=TSS)

    responses = [
        req_api.get(QUEUE),
        req_api.get(by_event()),
        req_api.get(one(ROW_A["id"])),
    ]

    assert [r.status_code for r in responses] == [401, 401, 401]
    assert seeded.requirement_queries() == []


# AC6-N8 (negative): an unreachable eventRequestService on a Coordinator read is a 502 with no data
def test_event_service_down_on_coordinator_read(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_coordinator", user_id=C1)
    req_events.error = httpx.ConnectError("connection refused")

    response = req_api.get(by_event(), headers=bearer())

    assert response.status_code == 502
    assert response.json() == {"detail": "Event request service unavailable"}


# AC2-H5 (happy, SCRUM-60): the Safety Officer lists an event's requirements for
# its safety check without being assigned to the event.
def test_safety_officer_lists_event_requirements(
    req_api: TestClient, seeded: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("safety_officer", user_id=TSS)

    response = req_api.get(by_event(), headers=bearer())

    assert response.status_code == 200
    assert ids(response) == [ROW_A["id"], ROW_B["id"]]
    assert req_events.requests == []
