"""API tests for "Reserve Equipment for an Event" (SCRUM-13), AC1 to AC5.

POST /equipment-reservations reserves units of one catalogue row against one
equipment requirement; GET /equipment-reservations/by-event/{id} lists an
event's reservations for Technical Support.

Supabase is the in-memory ``ReservationStore``; authService and venueService
are stubbed at ``httpx.get``. The database function ``reserve_equipment``
(row lock and re-check, decision D6) is simulated by the store and proved
for real by database/verify_equipment_reservation_writes.sql.

Every test carries its case ID from docs/testcases/scrum_13_testcases.md.
Unless a test says otherwise, the base request reserves 5 of P10 against
REQ1 for a one-day event on Wed 14 Oct 2026 at Search Big Hall, so P10's
hold window is Tue 13 -> Wed 14.
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from reservations_support import (
    C1,
    E1,
    E2,
    MISSING,
    P10,
    PD,
    PH10,
    PL,
    PS10,
    PX,
    REQ1,
    REQ2,
    REQ3,
    S4,
    TSS,
    ReservationStore,
    Services,
    api_error,
    equipment,
    reservation,
)

from app.config import get_settings
from app.db import get_client
from app.main import app

URL = "/equipment-reservations"
AUTH = {"Authorization": "Bearer staff-token"}
TUE13, WED14 = "2026-10-13", "2026-10-14"


def body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requirement_id": REQ1,
        "equipment_id": P10,
        "quantity": 5,
        "start_date": WED14,
        "end_date": WED14,
        "venue_id": "v-big",
    }
    payload.update(overrides)
    return payload


def shortfall(requested: int, available: int) -> dict[str, Any]:
    return {
        "message": "Insufficient equipment available",
        "requested": requested,
        "available": available,
        "shortfall": requested - available,
    }


@pytest.fixture
def store() -> ReservationStore:
    return ReservationStore()


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> Iterator[Services]:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    stub = Services()
    monkeypatch.setattr(httpx, "get", stub.get)
    get_settings.cache_clear()
    yield stub
    get_settings.cache_clear()


@pytest.fixture
def api(store: ReservationStore, services: Services) -> Iterator[TestClient]:
    app.dependency_overrides[get_client] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def reserve(api: TestClient, **overrides: Any) -> httpx.Response:
    return api.post(URL, json=body(**overrides), headers=AUTH)


def assert_nothing_stored(store: ReservationStore, before: list[dict]) -> None:
    """No reservation call, no direct write, and the reservations unchanged."""
    assert store.rpc_calls == []
    assert store.writes == []
    assert store.reservations() == before


def assert_refused_before_lookups(store: ReservationStore, services: Services) -> None:
    assert store.queries == []
    assert store.rpc_calls == []
    assert services.venue_calls == []


# --- AC1: reservation against a recorded requirement ---------------------------


# AC1-H1 (happy): Technical Support reserves units against a requirement
def test_reserves_units_against_requirement(
    api: TestClient, store: ReservationStore
) -> None:
    requirements_before = store.requirements()

    response = reserve(api)

    assert response.status_code == 201
    assert store.rpc_calls == [
        (
            "reserve_equipment",
            {
                "p_requirement_id": REQ1,
                "p_equipment_id": P10,
                "p_quantity": 5,
                "p_collection_date": TUE13,
                "p_return_date": WED14,
                "p_created_by": TSS,
            },
        )
    ]
    assert store.writes == []
    assert store.requirements() == requirements_before


# AC1-P1 (partition): a user holding technical_support among other roles can reserve
def test_multi_role_staff_can_reserve(api: TestClient, services: Services) -> None:
    services.roles = ["event_operations_manager", "technical_support"]

    response = reserve(api)

    assert response.status_code == 201


# AC1-P2 (partition): a requirement can be met from several catalogue rows (D2)
def test_requirement_met_from_several_rows(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(PX, 3, TUE13, WED14, requirement_id=REQ1, event=E1))

    response = reserve(api, quantity=2)

    assert response.status_code == 201


# AC1-P3 (partition): row and requirement types match ignoring case and extra spaces
def test_type_match_ignores_case_and_spaces(
    api: TestClient, store: ReservationStore
) -> None:
    store.add_equipment(equipment(PL, type="projector "))

    response = reserve(api, equipment_id=PL)

    assert response.status_code == 201


# AC1-B1, AC1-B2 (boundary): up to the requirement's outstanding quantity is accepted (D3)
@pytest.mark.parametrize("quantity", [1, 2], ids=["AC1-B1", "AC1-B2"])
def test_up_to_outstanding_quantity_is_accepted(
    api: TestClient, store: ReservationStore, quantity: int
) -> None:
    # REQ1 needs 5 and already holds 3 from PX: 2 are outstanding.
    store.reserve(reservation(PX, 3, TUE13, WED14, requirement_id=REQ1, event=E1))

    response = reserve(api, quantity=quantity)

    assert response.status_code == 201
    assert store.rpc_calls[0][1]["p_quantity"] == quantity


# AC1-B3 (boundary): one above the outstanding quantity is refused
def test_over_outstanding_quantity_is_refused(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(PX, 3, TUE13, WED14, requirement_id=REQ1, event=E1))
    before = store.reservations()

    response = reserve(api, quantity=3)

    assert response.status_code == 409
    assert response.json() == {"detail": "Exceeds the equipment requirement"}
    assert_nothing_stored(store, before)


# AC1-B4 (boundary): quantity 0 is refused before any lookup
def test_quantity_zero_is_refused(
    api: TestClient, store: ReservationStore, services: Services
) -> None:
    response = reserve(api, quantity=0)

    assert response.status_code == 422
    assert_refused_before_lookups(store, services)


# AC1-N1 (negative): invalid quantities are refused before any lookup
@pytest.mark.parametrize(
    "quantity", [-1, 2.5, "five", None], ids=["minus-one", "fraction", "text", "null"]
)
def test_invalid_quantity_is_refused(
    api: TestClient, store: ReservationStore, services: Services, quantity: Any
) -> None:
    response = reserve(api, quantity=quantity)

    assert response.status_code == 422
    assert_refused_before_lookups(store, services)


def _without(field: str) -> dict[str, Any]:
    payload = body()
    del payload[field]
    return payload


# AC1-N2 (negative): missing or malformed fields are refused before any lookup
@pytest.mark.parametrize(
    "payload",
    [
        _without("requirement_id"),
        body(requirement_id="abc"),
        _without("equipment_id"),
        body(start_date="14/10/2026"),
        body(start_date=WED14, end_date=TUE13),
        _without("venue_id"),
    ],
    ids=[
        "no-requirement",
        "malformed-requirement",
        "no-equipment",
        "bad-date-format",
        "end-before-start",
        "no-venue",
    ],
)
def test_missing_or_malformed_fields_are_refused(
    api: TestClient,
    store: ReservationStore,
    services: Services,
    payload: dict[str, Any],
) -> None:
    response = api.post(URL, json=payload, headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(store, services)


# AC1-N3 (negative): an unknown requirement is not found
def test_unknown_requirement_is_not_found(
    api: TestClient, store: ReservationStore
) -> None:
    before = store.reservations()

    response = reserve(api, requirement_id=MISSING)

    assert response.status_code == 404
    assert response.json() == {"detail": "Equipment requirement not found"}
    assert_nothing_stored(store, before)


# AC1-N4 (negative): an unknown catalogue row is not found
def test_unknown_equipment_is_not_found(
    api: TestClient, store: ReservationStore
) -> None:
    before = store.reservations()

    response = reserve(api, equipment_id=MISSING)

    assert response.status_code == 404
    assert response.json() == {"detail": "Equipment not found"}
    assert_nothing_stored(store, before)


# AC1-N5 (negative): a row whose type differs from the requirement is refused
def test_type_mismatch_is_refused(api: TestClient, store: ReservationStore) -> None:
    before = store.reservations()

    response = reserve(api, equipment_id=S4, quantity=2)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Equipment type does not match the requirement"
    }
    assert_nothing_stored(store, before)


# AC1-N6 (negative): an unknown venue is not found
def test_unknown_venue_is_not_found(api: TestClient, store: ReservationStore) -> None:
    before = store.reservations()

    response = reserve(api, venue_id="v-missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}
    assert_nothing_stored(store, before)


# AC1-N7 (negative): venueService unreachable or failing is a 502
@pytest.mark.parametrize("failure", ["unreachable", "server-error"], ids=["unreachable", "500"])
def test_venue_service_failure_is_bad_gateway(
    api: TestClient, store: ReservationStore, services: Services, failure: str
) -> None:
    if failure == "unreachable":
        services.venues_error = httpx.ConnectError("venueService down")
    else:
        services.venues_response = httpx.Response(500)
    before = store.reservations()

    response = reserve(api)

    assert response.status_code == 502
    assert response.json() == {"detail": "Venue service unavailable"}
    assert_nothing_stored(store, before)


# AC1-N8 (negative): a database failure on the read or on the reservation is a clean 500
@pytest.mark.parametrize("where", ["read", "rpc"], ids=["requirement-read", "reserve-rpc"])
def test_database_failure_is_server_error(
    api: TestClient, store: ReservationStore, where: str
) -> None:
    if where == "read":
        store.errors["equipment_requirements"] = api_error("XX000")
    else:
        store.rpc_error = api_error("XX000")
    before = store.reservations()

    response = reserve(api)

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed"}
    assert store.writes == []
    assert store.reservations() == before


# AC1-N12 (negative): a type mismatch caught only under the lock (D12) is a 422, not a 500
def test_type_mismatch_under_lock_is_unprocessable(
    api: TestClient, store: ReservationStore
) -> None:
    store.rpc_error = api_error("22023")
    before = store.reservations()

    response = reserve(api)

    assert response.status_code == 422
    assert response.json() == {"detail": "Equipment type does not match the requirement"}
    assert store.writes == []
    assert store.reservations() == before


# AC1-N13 (negative): an empty result from reserve_equipment is a clean 500
def test_empty_reservation_result_is_server_error(
    api: TestClient, store: ReservationStore
) -> None:
    store.rpc_result = []

    response = reserve(api)

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed"}


# AC1-X1 (cross-cutting): reserving requires a session
def test_reserving_requires_a_session(
    api: TestClient, store: ReservationStore, services: Services
) -> None:
    response = api.post(URL, json=body())

    assert response.status_code == 401
    assert_refused_before_lookups(store, services)


# AC1-X2 (cross-cutting): roles other than Technical Support may not reserve
@pytest.mark.parametrize(
    "role", ["event_coordinator", "venue_staff", "attendee"],
    ids=["coordinator", "venue-staff", "attendee"],
)
def test_other_roles_may_not_reserve(
    api: TestClient, store: ReservationStore, services: Services, role: str
) -> None:
    services.roles = [role]
    services.user_id = C1

    response = reserve(api)

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert_refused_before_lookups(store, services)


# --- AC2: only working equipment can be reserved -------------------------------


# AC2-P1, AC2-P2, AC2-P3, AC2-P4 (partition): a row that is not AVAILABLE is refused
@pytest.mark.parametrize(
    "status",
    ["DAMAGED", "UNDER_REPAIR", "UNDER_MAINTENANCE", "RETIRED"],
    ids=["AC2-P1", "AC2-P2", "AC2-P3", "AC2-P4"],
)
def test_unavailable_status_is_refused(
    api: TestClient, store: ReservationStore, status: str
) -> None:
    store.add_equipment(equipment(PD, status=status))
    before = store.reservations()

    response = reserve(api, equipment_id=PD)

    assert response.status_code == 409
    assert response.json() == {"detail": "Equipment not available"}
    assert_nothing_stored(store, before)


# AC2-X1 (cross-cutting): status is checked on the chosen row, not the type
def test_damaged_row_refused_although_type_has_free_units(
    api: TestClient, store: ReservationStore
) -> None:
    store.add_equipment(equipment(PD, status="DAMAGED"))  # P10 is free
    before = store.reservations()

    response = reserve(api, equipment_id=PD)

    assert response.status_code == 409
    assert response.json() == {"detail": "Equipment not available"}
    assert_nothing_stored(store, before)


# AC2-N1 (negative): a refusal under the row lock (D6) is a 409, not a 500
def test_refusal_under_lock_is_conflict(
    api: TestClient, store: ReservationStore
) -> None:
    store.rpc_error = api_error("P0004")
    before = store.reservations()

    response = reserve(api)

    assert response.status_code == 409
    assert response.json() == {"detail": "Equipment no longer available"}
    assert store.writes == []
    assert store.reservations() == before


# --- AC3: units held for an overlapping hold are not offered again -------------


# AC3-H1 (happy): units reserved for an overlapping event are withheld; the rest can be reserved
def test_remaining_units_can_be_reserved(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(P10, 6, TUE13, WED14))

    response = reserve(api, quantity=4)

    assert response.status_code == 201


# AC3-H2 (happy): the endpoint reads the chosen row's reservations over its hold window
def test_reads_row_reservations_over_hold_window(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(P10, 6, TUE13, WED14))

    reserve(api, quantity=4)

    window_reads = [
        q["filters"]
        for q in store.reservation_queries()
        if ("equipment_id", "eq", P10) in q["filters"]
    ]
    assert window_reads, "no reservation query filtered on the chosen row"
    assert any(
        ("collection_date", "lte", WED14) in f and ("return_date", "gte", TUE13) in f
        for f in window_reads
    )


# AC3-P3 (partition): units held by another requirement of the same event still count
def test_same_event_other_requirement_still_counts(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(P10, 6, TUE13, WED14, requirement_id=REQ3, event=E1))
    before = store.reservations()

    response = reserve(api, quantity=5)

    assert response.status_code == 409
    assert response.json() == {"detail": shortfall(5, 4)}
    assert_nothing_stored(store, before)


# --- AC4: the reservation records equipment, quantity, event and period --------


# AC4-H1 (happy): the response is the stored reservation, event taken from the requirement
def test_response_is_the_stored_reservation(
    api: TestClient, store: ReservationStore
) -> None:
    response = reserve(api)

    assert response.status_code == 201
    stored = store.reservations()
    assert len(stored) == 1
    assert response.json() == stored[0]
    data = response.json()
    assert {
        key: data[key]
        for key in (
            "requirement_id",
            "event_request_id",
            "equipment_id",
            "quantity",
            "collection_date",
            "return_date",
            "created_by",
        )
    } == {
        "requirement_id": REQ1,
        "event_request_id": E1,
        "equipment_id": P10,
        "quantity": 5,
        "collection_date": TUE13,
        "return_date": WED14,
        "created_by": TSS,
    }
    assert data["id"] and data["created_at"]


# AC4-P1 (partition): a multi-day event returns on its last day
def test_multi_day_event_returns_on_last_day(
    api: TestClient, store: ReservationStore
) -> None:
    response = reserve(api, end_date="2026-10-16")

    assert response.status_code == 201
    params = store.rpc_calls[0][1]
    assert (params["p_collection_date"], params["p_return_date"]) == (
        TUE13,
        "2026-10-16",
    )


# AC4-P2, AC4-P3 (partition): the transfer day applies only to a row in another building
@pytest.mark.parametrize(
    ("equipment_id", "collection"),
    [(PH10, "2026-10-12"), (PS10, TUE13)],
    ids=["AC4-P2", "AC4-P3"],
)
def test_collection_date_follows_row_building(
    api: TestClient, store: ReservationStore, equipment_id: str, collection: str
) -> None:
    response = reserve(api, equipment_id=equipment_id)

    assert response.status_code == 201
    assert store.rpc_calls[0][1]["p_collection_date"] == collection


# AC4-X1 (cross-cutting): the caller cannot choose the event
def test_caller_cannot_choose_event(
    api: TestClient, store: ReservationStore, services: Services
) -> None:
    response = api.post(URL, json={**body(), "event_request_id": E2}, headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(store, services)


# AC4-X2 (cross-cutting): the caller cannot choose who made the reservation
def test_caller_cannot_choose_creator(
    api: TestClient, store: ReservationStore, services: Services
) -> None:
    response = api.post(URL, json={**body(), "created_by": C1}, headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(store, services)


# AC4-H3 (happy): Technical Support lists an event's reservations, oldest first
def test_lists_event_reservations_oldest_first(
    api: TestClient, store: ReservationStore
) -> None:
    middle = reservation(P10, 2, TUE13, WED14, requirement_id=REQ1, event=E1,
                         created_at="2026-10-12T10:00:00+08:00")
    newest = reservation(S4, 2, TUE13, WED14, requirement_id=REQ2, event=E1,
                         created_at="2026-10-12T11:00:00+08:00")
    oldest = reservation(PX, 3, TUE13, WED14, requirement_id=REQ1, event=E1,
                         created_at="2026-10-12T09:00:00+08:00")
    other = reservation(P10, 6, TUE13, WED14)  # E2
    store.reserve(middle, newest, other, oldest)

    response = api.get(f"{URL}/by-event/{E1}", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == [oldest, middle, newest]


# AC4-P4 (partition): an event with no reservations returns an empty list
def test_event_without_reservations_is_empty(api: TestClient) -> None:
    response = api.get(f"{URL}/by-event/{E1}", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == []


# AC4-N1 (negative): a malformed event id is refused before any lookup
def test_malformed_event_id_is_refused(
    api: TestClient, store: ReservationStore, services: Services
) -> None:
    response = api.get(f"{URL}/by-event/abc", headers=AUTH)

    assert response.status_code == 422
    assert store.queries == []


# AC4-X3 (cross-cutting): only Technical Support may list reservations
@pytest.mark.parametrize(
    ("headers", "role", "status"),
    [({}, "technical_support", 401), (AUTH, "event_coordinator", 403)],
    ids=["no-session", "coordinator"],
)
def test_only_staff_may_list(
    api: TestClient,
    store: ReservationStore,
    services: Services,
    headers: dict[str, str],
    role: str,
    status: int,
) -> None:
    services.roles = [role]

    response = api.get(f"{URL}/by-event/{E1}", headers=headers)

    assert response.status_code == status
    assert store.queries == []


# --- AC5: a shortfall is refused and reported ----------------------------------


# AC5-H1 (happy): a request over what is free is refused with the numbers
def test_shortfall_is_refused_and_reported(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(P10, 8, TUE13, WED14))
    before = store.reservations()

    response = reserve(api, quantity=5)

    assert response.status_code == 409
    assert response.json() == {"detail": shortfall(5, 2)}
    assert_nothing_stored(store, before)


# AC5-B1 (boundary): one more than available is refused with a shortfall of 1
def test_one_over_available_is_refused(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(P10, 6, TUE13, WED14))
    before = store.reservations()

    response = reserve(api, quantity=5)

    assert response.status_code == 409
    assert response.json() == {"detail": shortfall(5, 4)}
    assert_nothing_stored(store, before)


# AC5-B2, AC5-B3 (boundary): exactly and one fewer than available are accepted
@pytest.mark.parametrize("quantity", [4, 3], ids=["AC5-B2", "AC5-B3"])
def test_at_or_below_available_is_accepted(
    api: TestClient, store: ReservationStore, quantity: int
) -> None:
    store.reserve(reservation(P10, 6, TUE13, WED14))

    response = reserve(api, quantity=quantity)

    assert response.status_code == 201
    assert store.rpc_calls[0][1]["p_quantity"] == quantity


# AC5-P1 (partition): nothing free, so the shortfall is the whole request
def test_nothing_free_shortfall_is_whole_request(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(P10, 10, TUE13, WED14))
    before = store.reservations()

    response = reserve(api, quantity=5)

    assert response.status_code == 409
    assert response.json() == {"detail": shortfall(5, 0)}
    assert_nothing_stored(store, before)


# AC5-P2 (partition): a shortfall on one requirement does not block another (Q&A #90)
def test_shortfall_does_not_block_other_requirement(
    api: TestClient, store: ReservationStore
) -> None:
    store.reserve(reservation(P10, 6, TUE13, WED14))

    refused = reserve(api, quantity=5)
    accepted = reserve(api, requirement_id=REQ2, equipment_id=S4, quantity=2)

    assert refused.status_code == 409
    assert accepted.status_code == 201
    assert [params["p_requirement_id"] for _, params in store.rpc_calls] == [REQ2]


# AC5-P3 (partition): availability is the chosen row's, not the type's (D4)
def test_availability_is_per_row(api: TestClient, store: ReservationStore) -> None:
    store.reserve(reservation(P10, 6, TUE13, WED14))  # PX still has 6 free
    before = store.reservations()

    response = reserve(api, quantity=5)

    assert response.status_code == 409
    assert response.json() == {"detail": shortfall(5, 4)}
    assert_nothing_stored(store, before)


# AC5-N1 (negative): a refused reservation leaves existing reservations unchanged
def test_refusal_leaves_existing_reservations_unchanged(
    api: TestClient, store: ReservationStore
) -> None:
    held = reservation(P10, 6, TUE13, WED14)
    store.reserve(held)

    response = reserve(api, quantity=5)
    listed = api.get(f"{URL}/by-event/{E2}", headers=AUTH)

    assert response.status_code == 409
    assert listed.status_code == 200
    assert listed.json() == [held]
    assert store.writes == []


# AC2-H6 (happy, SCRUM-60): the Safety Officer lists an event's reservations for
# its safety check.
def test_safety_officer_lists_event_reservations(
    api: TestClient, store: ReservationStore, services: Services
) -> None:
    row = reservation(P10, 2, TUE13, WED14, requirement_id=REQ1, event=E1)
    store.reserve(row)
    services.roles = ["safety_officer"]

    response = api.get(f"{URL}/by-event/{E1}", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == [row]


# AC2-N3 (negative, SCRUM-60): reading is all the Safety Officer can do; reserving
# stays Technical Support's.
def test_safety_officer_cannot_reserve(
    api: TestClient, store: ReservationStore, services: Services
) -> None:
    before = list(store.rows.get("equipment_reservations", []))
    services.roles = ["safety_officer"]

    response = reserve(api)

    assert response.status_code == 403
    assert_nothing_stored(store, before)
