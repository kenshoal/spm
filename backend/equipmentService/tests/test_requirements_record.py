"""Recording tests for "Record Equipment Requirements for an Event" (SCRUM-33).

POST /equipment-requirements. Every test carries its case ID from
docs/testcases/scrum_33_testcases.md. "Nothing stored" means the store saw
no insert and no RPC; "no lookup" means eventRequestService was not called.
"""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from requirements_support import (
    C1,
    C2,
    E1,
    GALA_DATES,
    FakeEventService,
    RequirementsStore,
    api_error,
    bearer,
)

URL = "/equipment-requirements"
_OMIT = object()


def body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_request_id": E1,
        "equipment_type": "Projector",
        "quantity": 2,
        "technical_requirements": "HDMI, 4K",
    }
    for key, value in overrides.items():
        if value is _OMIT:
            payload.pop(key, None)
        else:
            payload[key] = value
    return payload


@pytest.fixture
def coordinator(as_user) -> None:
    as_user("event_coordinator", user_id=C1)


def post(api: TestClient, payload: dict[str, Any]) -> httpx.Response:
    return api.post(URL, json=payload, headers=bearer())


# AC1-H3 (happy): the assigned Coordinator records a requirement linked to the event, with the event snapshot
def test_assigned_coordinator_records_a_requirement(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    response = post(req_api, body())

    assert response.status_code == 201
    data = response.json()
    assert data["id"]
    assert data["recorded_at"]
    assert {k: v for k, v in data.items() if k not in ("id", "recorded_at")} == {
        "event_request_id": E1,
        "equipment_type": "Projector",
        "quantity": 2,
        "technical_requirements": "HDMI, 4K",
        "status": "requested",
        "support_note": None,
        "event_name": "Annual Gala",
        "event_date_times": GALA_DATES,
        "recorded_by": C1,
        "updated_by": None,
        "updated_at": None,
        "essential": True,
        "essential_note": None,
    }
    assert req_store.inserts == [
        (
            "equipment_requirements",
            {
                "event_request_id": E1,
                "equipment_type": "Projector",
                "quantity": 2,
                "technical_requirements": "HDMI, 4K",
                "event_name": "Annual Gala",
                "event_date_times": GALA_DATES,
                "recorded_by": C1,
            },
        )
    ]
    assert req_store.rpc_calls == []
    assert req_events.paths() == [
        f"/event-requests/{E1}/coordinator",
        f"/event-requests/{E1}",
    ]


# AC1-H4 (happy): technical requirements are optional
def test_technical_requirements_are_optional(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    response = post(req_api, body(technical_requirements=_OMIT))

    assert response.status_code == 201
    assert response.json()["technical_requirements"] is None
    assert req_store.inserts[0][1]["technical_requirements"] is None


# AC1-P1 (partition): the type is matched ignoring case and spaces and stored in the catalogue's spelling
def test_type_is_matched_loosely_and_stored_as_catalogued(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    response = post(req_api, body(equipment_type="  projector "))

    assert response.status_code == 201
    assert response.json()["equipment_type"] == "Projector"
    assert req_store.inserts[0][1]["equipment_type"] == "Projector"


# AC1-P2 (partition): a type whose only units are damaged is still accepted (availability is SCRUM-13)
def test_type_with_only_damaged_units_is_accepted(
    req_api: TestClient, coordinator
) -> None:
    response = post(req_api, body(equipment_type="Wireless Microphone"))

    assert response.status_code == 201
    assert response.json()["equipment_type"] == "Wireless Microphone"


# AC1-P3 (partition): a quantity above what is owned is accepted (the shortfall is SCRUM-13's)
def test_quantity_above_owned_is_accepted(req_api: TestClient, coordinator) -> None:
    response = post(req_api, body(quantity=50))

    assert response.status_code == 201
    assert response.json()["quantity"] == 50


# AC1-P4 (partition): a second requirement of the same type for the same event coexists
def test_same_type_twice_coexists(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    first = post(req_api, body())
    second = post(req_api, body())

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert len(req_store.inserts) == 2


# AC6-P1 to AC6-P3 (partition): each status in the allow-list accepts a requirement
@pytest.mark.parametrize(
    "event_status",
    ["Approved", "Planning", "Safety Review"],
    ids=["AC6-P1", "AC6-P2", "AC6-P3"],
)
def test_open_event_statuses_accept_requirements(
    req_api: TestClient, req_events: FakeEventService, coordinator, event_status: str
) -> None:
    req_events.event["status"] = event_status

    response = post(req_api, body())

    assert response.status_code == 201


# AC1-N6 to AC1-N9 (negative): server-owned fields cannot be set by the caller
@pytest.mark.parametrize(
    "extra",
    [{"recorded_by": C2}, {"status": "arranged"}, {"event_name": "Fake"}, {"support_note": "x"}],
    ids=["AC1-N6", "AC1-N7", "AC1-N8", "AC1-N9"],
)
def test_server_owned_fields_are_forbidden(
    req_api: TestClient,
    req_store: RequirementsStore,
    req_events: FakeEventService,
    coordinator,
    extra: dict[str, Any],
) -> None:
    response = post(req_api, {**body(), **extra})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC1-N10 (negative): a request without a bearer token is refused before anything else
def test_record_requires_authentication(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_coordinator")

    response = req_api.post(URL, json=body())

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC1-X2 (cross-cutting): a store failure is a 500 and nothing is reported as created
def test_store_failure_is_not_reported_as_created(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    req_store.errors["equipment_requirements"] = api_error("XX000")

    response = post(req_api, body())

    assert response.status_code == 500
    assert response.json()["detail"] == "Database operation failed"


# AC2-B6 (boundary): quantity 0, just below the minimum, is refused before any lookup
def test_quantity_zero_is_refused(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    response = post(req_api, body(quantity=0))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "quantity"]
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC2-B7 (boundary): quantity 1, the minimum, is accepted
def test_quantity_one_is_accepted(req_api: TestClient, coordinator) -> None:
    response = post(req_api, body(quantity=1))

    assert response.status_code == 201
    assert response.json()["quantity"] == 1


# AC2-B8 (boundary): the largest integer the column holds is accepted
def test_quantity_at_integer_max_is_accepted(req_api: TestClient, coordinator) -> None:
    response = post(req_api, body(quantity=2_147_483_647))

    assert response.status_code == 201


# AC2-B9 (boundary): one above the column's integer max is refused
def test_quantity_above_integer_max_is_refused(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    response = post(req_api, body(quantity=2_147_483_648))

    assert response.status_code == 422
    assert req_store.nothing_stored()


# AC2-N2 to AC2-N5 (negative): a quantity that is not a whole number is refused
@pytest.mark.parametrize(
    "quantity",
    ["abc", 1.5, None, _OMIT],
    ids=["AC2-N2", "AC2-N3", "AC2-N4", "AC2-N5"],
)
def test_non_whole_quantity_is_refused(
    req_api: TestClient,
    req_store: RequirementsStore,
    req_events: FakeEventService,
    coordinator,
    quantity: object,
) -> None:
    response = post(req_api, body(quantity=quantity))

    assert response.status_code == 422
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC2-N6 to AC2-N8 (negative): a missing, null or blank type is refused before any lookup
@pytest.mark.parametrize(
    "equipment_type", [_OMIT, None, "   "], ids=["AC2-N6", "AC2-N7", "AC2-N8"]
)
def test_missing_or_blank_type_is_refused(
    req_api: TestClient,
    req_store: RequirementsStore,
    req_events: FakeEventService,
    coordinator,
    equipment_type: object,
) -> None:
    response = post(req_api, body(equipment_type=equipment_type))

    assert response.status_code == 422
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC2-N9 (negative): a type that is not in the catalogue is refused
def test_unknown_type_is_refused(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    response = post(req_api, body(equipment_type="Hologram"))

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown equipment type"
    assert req_store.nothing_stored()


# AC2-N10 (negative): a type whose only rows are retired counts as unknown
def test_retired_only_type_is_unknown(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    response = post(req_api, body(equipment_type="Fog Machine"))

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown equipment type"
    assert req_store.nothing_stored()


# AC2-B10 (boundary): technical requirements of exactly 2,000 characters are accepted
def test_technical_requirements_at_limit_are_accepted(
    req_api: TestClient, coordinator
) -> None:
    response = post(req_api, body(technical_requirements="x" * 2000))

    assert response.status_code == 201
    assert len(response.json()["technical_requirements"]) == 2000


# AC2-B11 (boundary): technical requirements of 2,001 characters are refused before any lookup
def test_technical_requirements_over_limit_are_refused(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    response = post(req_api, body(technical_requirements="x" * 2001))

    assert response.status_code == 422
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC2-P1 (partition): blank technical requirements are stored as none
def test_blank_technical_requirements_become_none(
    req_api: TestClient, req_store: RequirementsStore, coordinator
) -> None:
    response = post(req_api, body(technical_requirements="   "))

    assert response.status_code == 201
    assert response.json()["technical_requirements"] is None
    assert req_store.inserts[0][1]["technical_requirements"] is None


# AC2-N11, AC2-N12 (negative): an event reference that is not a UUID, or is missing, is refused before any lookup
@pytest.mark.parametrize(
    "event_request_id", ["not-a-uuid", _OMIT], ids=["AC2-N11", "AC2-N12"]
)
def test_invalid_event_reference_is_refused(
    req_api: TestClient,
    req_store: RequirementsStore,
    req_events: FakeEventService,
    coordinator,
    event_request_id: object,
) -> None:
    response = post(req_api, body(event_request_id=event_request_id))

    assert response.status_code == 422
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC6-N1 to AC6-N10 (negative): every status outside Approved, Planning and Safety
# Review refuses a new requirement (409) and stores nothing
@pytest.mark.parametrize(
    "event_status",
    [
        "Draft", "Submitted", "Under Review", "Changes Requested", "Confirmed",
        "Completed", "Cancelled", "Rejected", "Withdrawn", "Postponed",
    ],
    ids=[f"AC6-N{k}" for k in range(1, 11)],
)
def test_closed_event_refuses_requirements(
    req_api: TestClient,
    req_store: RequirementsStore,
    req_events: FakeEventService,
    coordinator,
    event_status: str,
) -> None:
    req_events.event["status"] = event_status

    response = post(req_api, body())

    assert response.status_code == 409
    assert response.json()["detail"] == "Event is closed"
    assert req_store.nothing_stored()


def _not_found_body(req_api: TestClient, req_events: FakeEventService) -> Any:
    req_events.coordinator_reply = httpx.Response(404, json={"detail": "Not found"})
    req_events.event_reply = httpx.Response(404, json={"detail": "Not found"})
    return post(req_api, body()).json()


# AC6-X8 (cross-cutting): a Coordinator who is not assigned to the event is refused as not found
def test_unassigned_coordinator_is_refused(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    req_events.coordinator_id = C2

    response = post(req_api, body())

    assert response.status_code == 404
    assert response.json() == {"detail": "Event request not found"}
    assert req_store.nothing_stored()


# AC6-X9 (cross-cutting): an event with no Coordinator yet gives the same 404 as an unassigned one
def test_event_without_coordinator_is_not_found(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    req_events.coordinator_reply = httpx.Response(404, json={"detail": "No coordinator"})

    response = post(req_api, body())

    assert response.status_code == 404
    assert response.json() == {"detail": "Event request not found"}
    assert req_store.nothing_stored()


# AC6-X10 (cross-cutting): an event that does not exist is indistinguishable from an unassigned one
def test_unknown_event_is_indistinguishable(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    response = _not_found_body(req_api, req_events)

    assert response == {"detail": "Event request not found"}
    assert req_store.nothing_stored()


# AC6-X11 (cross-cutting): an owning organiser who also holds the coordinator role but is not assigned is refused
def test_organiser_coordinator_not_assigned_is_refused(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, as_user
) -> None:
    as_user("event_organiser", "event_coordinator", user_id=C1)
    req_events.event["organiser_id"] = C1
    req_events.coordinator_id = C2

    response = post(req_api, body())

    assert response.status_code == 404
    assert response.json() == {"detail": "Event request not found"}
    assert req_events.paths() == [f"/event-requests/{E1}/coordinator"]
    assert req_store.nothing_stored()


# AC6-X12 to AC6-X16 (cross-cutting): no other role may record, and eventRequestService is not asked
@pytest.mark.parametrize(
    "role",
    ["technical_support", "event_organiser", "venue_staff", "event_operations_manager", "attendee"],
    ids=["AC6-X12", "AC6-X13", "AC6-X14", "AC6-X15", "AC6-X16"],
)
def test_other_roles_cannot_record(
    req_api: TestClient,
    req_store: RequirementsStore,
    req_events: FakeEventService,
    as_user,
    role: str,
) -> None:
    as_user(role)

    response = post(req_api, body())

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    assert req_store.nothing_stored()
    assert req_events.requests == []


# AC6-N6 (negative): an unreachable eventRequestService is a 502 and nothing is stored
def test_event_service_down_on_record(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    req_events.error = httpx.ConnectError("connection refused")

    response = post(req_api, body())

    assert response.status_code == 502
    assert response.json()["detail"] == "Event request service unavailable"
    assert req_store.nothing_stored()


# AC6-N7 (negative): a 401 from eventRequestService on record is an invalid session
def test_event_service_unauthorised_on_record(
    req_api: TestClient, req_store: RequirementsStore, req_events: FakeEventService, coordinator
) -> None:
    req_events.coordinator_reply = httpx.Response(401, json={"detail": "Invalid session"})

    response = post(req_api, body())

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid session"
    assert req_store.nothing_stored()
