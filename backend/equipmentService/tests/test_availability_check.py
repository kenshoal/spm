"""API tests for POST /equipment/availability-check (SCRUM-10).

Test-case IDs trace to docs/testcases/scrum_10_testcases.md. Supabase is
replaced by FakeSupabase; authService and venueService are stubbed at
httpx.get, the same seam deps.py uses.
"""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.config import get_settings

USER_ID = "11111111-1111-1111-1111-111111111111"
URL = "/equipment/availability-check"
AUTH = {"Authorization": "Bearer staff-token"}

# The shape of venueService GET /venues/locations (SCRUM-13 D11).
VENUES_JSON: list[dict[str, Any]] = [
    {"id": "v-big", "name": "Search Big Hall", "location": "Search Wing"},
    {"id": "v-small", "name": "Search Small Room", "location": "Search Wing"},
    {"id": "v-closed", "name": "Search Closed Hall", "location": "Search Wing"},
    {"id": "v-harbour", "name": "Harbour Room", "location": "Harbour Block"},
]


def equipment(
    id: str = "p10",
    type: str = "Projector",
    qty: int = 10,
    home: str = "Store Room B",
) -> dict[str, Any]:
    return {
        "id": id,
        "type": type,
        "total_owned_quantity": qty,
        "home_location": home,
        "operational_status": "AVAILABLE",
    }


def reservation(equipment_id: str, qty: int, collect: str, ret: str) -> dict[str, Any]:
    return {
        "equipment_id": equipment_id,
        "quantity": qty,
        "collection_date": collect,
        "return_date": ret,
    }


P10 = equipment()
S4 = equipment(id="s4", type="Speaker", qty=4)


def body(**overrides: Any) -> dict[str, Any]:
    return {
        "start_date": "2026-10-14",
        "end_date": "2026-10-14",
        "venue_id": "v-big",
        "items": [{"type": "Projector", "quantity": 5}],
        **overrides,
    }


def result(requested: int, available: int, shortfall: int) -> dict[str, int]:
    return {"requested": requested, "available": available, "shortfall": shortfall}


class Services:
    """Stubs authService /auth/me and venueService GET /venues/locations."""

    def __init__(self) -> None:
        self.roles = ["technical_support"]
        self.venues_response = httpx.Response(200, json=VENUES_JSON)
        self.venues_error: Exception | None = None
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: Any, *args: Any, **kwargs: Any) -> httpx.Response:
        url = str(url)
        self.calls.append((url, dict(kwargs.get("headers") or {})))
        if url.endswith("/auth/me"):
            return httpx.Response(
                200, json={"id": USER_ID, "role": self.roles[0], "roles": self.roles}
            )
        if url.rstrip("/").endswith("/venues/locations"):
            if self.venues_error is not None:
                raise self.venues_error
            return self.venues_response
        raise AssertionError(f"unexpected GET {url}")

    @property
    def venue_calls(self) -> list[tuple[str, dict[str, str]]]:
        return [
            c for c in self.calls if c[0].rstrip("/").endswith("/venues/locations")
        ]


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    stub = Services()
    monkeypatch.setattr(httpx, "get", stub.get)
    get_settings.cache_clear()
    yield stub
    get_settings.cache_clear()


def seed(fake_client, rows: list[dict[str, Any]], reservations=()) -> None:
    fake_client.table_data["equipment"] = rows
    fake_client.table_data["equipment_reservations"] = list(reservations)


def assert_nothing_written(fake_client) -> None:
    assert fake_client.inserts == []
    assert fake_client.updates == []
    assert fake_client.rpc_calls == []


def assert_refused_before_lookups(services: Services, fake_client) -> None:
    assert services.venue_calls == []
    assert fake_client.tables_queried == []


# --- AC1 ---------------------------------------------------------------------


# AC1-H2 (happy): the endpoint wires venueService, both queries and the calculation
def test_check_returns_result_per_type(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10, S4])

    response = client.post(
        URL,
        json=body(items=[{"type": "Projector", "quantity": 5}, {"type": "Speaker", "quantity": 2}]),
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json() == {"Projector": result(5, 10, 0), "Speaker": result(2, 4, 0)}
    assert len(services.venue_calls) == 1
    assert services.venue_calls[0][1].get("Authorization") == "Bearer staff-token"
    assert ("operational_status", "AVAILABLE") in fake_client.filters
    assert_nothing_written(fake_client)


# AC1-P4, AC6 (partition): an unknown type is reported unavailable, not an error
def test_unknown_type_reported_unavailable(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(
        URL,
        json=body(items=[{"type": "Projector", "quantity": 5}, {"type": "Hologram", "quantity": 3}]),
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json() == {"Projector": result(5, 10, 0), "Hologram": result(3, 0, 3)}
    assert_nothing_written(fake_client)


# AC1-P5 (partition): a past start date is allowed (Discussion #25)
def test_past_start_date_is_allowed(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(
        URL, json=body(start_date="2026-10-01", end_date="2026-10-01"), headers=AUTH
    )

    assert response.status_code == 200
    assert response.json() == {"Projector": result(5, 10, 0)}


# AC1-B1 (boundary): a one-day event (end = start) is accepted
def test_one_day_event_is_accepted(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(start_date="2026-10-14", end_date="2026-10-14"), headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"Projector": result(5, 10, 0)}


# AC1-B2 (boundary): end one day before start is refused before any lookup
def test_end_before_start_is_refused(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(start_date="2026-10-14", end_date="2026-10-13"), headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(services, fake_client)


# AC1-B3 (boundary): quantity 1 is accepted
def test_quantity_one_is_accepted(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(items=[{"type": "Projector", "quantity": 1}]), headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"Projector": result(1, 10, 0)}


# AC1-B4 (boundary): quantity 0 is refused before any lookup
def test_quantity_zero_is_refused(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(items=[{"type": "Projector", "quantity": 0}]), headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(services, fake_client)


# AC1-N1 (negative): negative, fractional and non-numeric quantities are refused
@pytest.mark.parametrize("quantity", [-1, 2.5, "five"], ids=["minus-one", "fraction", "text"])
def test_invalid_quantity_is_refused(client: TestClient, fake_client, services, quantity: Any) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(items=[{"type": "Projector", "quantity": quantity}]), headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(services, fake_client)


# AC1-N2 (negative): an empty item list is refused
def test_empty_items_are_refused(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(items=[]), headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(services, fake_client)


# AC1-N3 (negative): duplicate types are refused, compared with norm()
@pytest.mark.parametrize(
    "types",
    [["Projector", "Projector"], ["Projector", " projector "]],
    ids=["exact", "case-and-space"],
)
def test_duplicate_types_are_refused(client: TestClient, fake_client, services, types: list[str]) -> None:
    seed(fake_client, [P10])

    response = client.post(
        URL, json=body(items=[{"type": t, "quantity": 1} for t in types]), headers=AUTH
    )

    assert response.status_code == 422
    assert_refused_before_lookups(services, fake_client)


# AC1-N4 (negative): missing or malformed fields are refused
@pytest.mark.parametrize(
    "payload",
    [
        {k: v for k, v in body().items() if k != "venue_id"},
        body(start_date="14/10/2026"),
        body(end_date="2026-11-31"),
        {k: v for k, v in body().items() if k != "items"},
    ],
    ids=["no-venue", "wrong-format", "impossible-date", "no-items"],
)
def test_missing_or_malformed_fields_are_refused(
    client: TestClient, fake_client, services, payload: dict[str, Any]
) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=payload, headers=AUTH)

    assert response.status_code == 422
    assert_refused_before_lookups(services, fake_client)


# AC1-N5 (negative): an unknown venue is 404 and no equipment is queried
def test_unknown_venue_is_404(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(venue_id="v-missing"), headers=AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "Venue not found"
    assert fake_client.tables_queried == []


# AC1-N6 (negative): venueService rejecting the token is passed on as 401
def test_venue_service_rejecting_token_is_401(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])
    services.venues_response = httpx.Response(401, json={"detail": "Invalid session"})

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 401
    assert fake_client.tables_queried == []


# AC1-N7 (negative): venueService unreachable or failing is 502
@pytest.mark.parametrize("failure", ["unreachable", "server-error"])
def test_venue_service_failure_is_502(client: TestClient, fake_client, services, failure: str) -> None:
    seed(fake_client, [P10])
    if failure == "unreachable":
        services.venues_error = httpx.ConnectError("connection refused")
    else:
        services.venues_response = httpx.Response(500, json={"detail": "boom"})

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 502
    assert response.json()["detail"] == "Venue service unavailable"
    assert fake_client.tables_queried == []


# AC1-N8 (negative): a database failure is a clean 500, not a crash
def test_database_failure_is_500(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])
    fake_client.table_errors["equipment"] = APIError({"message": "boom", "code": "XX000"})

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 500
    assert response.json()["detail"] == "Database operation failed"
    assert_nothing_written(fake_client)


# AC1-X1 (cross-cutting): the check requires a session
def test_check_requires_session(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body())

    assert response.status_code == 401
    assert_refused_before_lookups(services, fake_client)


# AC1-X2 (cross-cutting): an event coordinator may not run the check
def test_coordinator_is_forbidden(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])
    services.roles = ["event_coordinator"]

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 403
    assert_refused_before_lookups(services, fake_client)


# AC1-X3 (cross-cutting): an Operations Manager who also holds technical_support may run it
def test_manager_with_technical_support_is_allowed(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])
    services.roles = ["event_operations_manager", "technical_support"]

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"Projector": result(5, 10, 0)}


# --- AC2, AC3, AC5, AC6 --------------------------------------------------------


# AC2-H2 (happy): the endpoint only reads AVAILABLE rows
def test_check_only_reads_available_rows(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 200
    assert ("operational_status", "AVAILABLE") in fake_client.filters
    assert_nothing_written(fake_client)


# AC3-H2 (happy): the endpoint subtracts fetched reservations
def test_check_subtracts_reservations(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10], [reservation("p10", 4, "2026-10-13", "2026-10-14")])

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"Projector": result(5, 6, 0)}
    assert_nothing_written(fake_client)


# AC3-B2, AC5 (boundary): reservations are fetched back to start - 1 - TRANSFER_DAYS
def test_reservation_query_uses_widest_hold_window(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 200
    assert "equipment_reservations" in fake_client.tables_queried
    assert ("equipment_id", "in", ["p10"]) in fake_client.filters
    assert ("collection_date", "lte", "2026-10-14") in fake_client.filters
    assert ("return_date", "gte", "2026-10-12") in fake_client.filters
    assert_nothing_written(fake_client)


# AC5-H2 (happy): the endpoint uses the venue list to apply the transfer day
def test_check_applies_transfer_day(client: TestClient, fake_client, services) -> None:
    seed(
        fake_client,
        [equipment(home="Harbour Room")],
        [reservation("p10", 10, "2026-10-10", "2026-10-12")],
    )

    response = client.post(URL, json=body(), headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"Projector": result(5, 0, 5)}


# AC6-H1 (happy): a shortfall is reported with 200, not refused with 409
def test_shortfall_is_reported_not_refused(client: TestClient, fake_client, services) -> None:
    seed(fake_client, [P10])

    response = client.post(URL, json=body(items=[{"type": "Projector", "quantity": 12}]), headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"Projector": result(12, 10, 2)}
    assert_nothing_written(fake_client)
