"""Shared fakes and data for the SCRUM-13 equipment-reservation tests.

Imported as ``reservations_support`` (CI runs plain ``pytest``, which puts
this folder on sys.path), like ``requirements_support``.

* ``ReservationStore`` stands in for the Supabase client. It holds the
  catalogue, the requirements and the reservations, applies ``eq``, ``neq``,
  ``in_``, ``lte``, ``gte``, ``order`` and ``limit`` to them, and logs every
  query. A router that forgets a filter reads the wrong rows and the test
  fails. ``reserve_equipment`` is simulated: it copies the event from the
  requirement and stores the row, as the database function will.
* ``Services`` stubs authService ``/auth/me`` and venueService
  ``GET /venues/locations`` (SCRUM-13 D11) at ``httpx.get``, the seam ``deps.py`` and ``venues_client.py`` use.

Case IDs trace to docs/testcases/scrum_13_testcases.md.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from postgrest.exceptions import APIError

TSS = "33333333-3333-3333-3333-333333333333"  # Technical Support Staff
C1 = "11111111-1111-1111-1111-111111111111"  # Event Coordinator
E1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"  # the event being reserved for
E2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"  # another event
MISSING = "99999999-9999-4999-8999-999999999999"

REQ1 = "b1300000-0000-4000-8000-000000000001"  # E1, Projector x5
REQ2 = "b1300000-0000-4000-8000-000000000002"  # E1, Speaker x2
REQ3 = "b1300000-0000-4000-8000-000000000003"  # E1, Projector x3
REQB = "b1300000-0000-4000-8000-00000000000b"  # E2, Projector x10

P10 = "e1300000-0000-4000-8000-000000000001"  # Projector x10, store stock
PX = "e1300000-0000-4000-8000-000000000002"  # Projector x6, store stock
PH10 = "e1300000-0000-4000-8000-000000000003"  # Projector x10, Harbour Room
PS10 = "e1300000-0000-4000-8000-000000000004"  # Projector x10, same building
S4 = "e1300000-0000-4000-8000-000000000005"  # Speaker x4, store stock
PD = "e1300000-0000-4000-8000-000000000006"  # Projector x10, status per test
PL = "e1300000-0000-4000-8000-000000000007"  # type "projector " (odd spacing)

# The shape of venueService GET /venues/locations (D11): id, name, location.
VENUES_JSON: list[dict[str, Any]] = [
    {"id": "v-big", "name": "Search Big Hall", "location": "Search Wing"},
    {"id": "v-small", "name": "Search Small Room", "location": "Search Wing"},
    {"id": "v-closed", "name": "Search Closed Hall", "location": "Search Wing"},
    {"id": "v-harbour", "name": "Harbour Room", "location": "Harbour Block"},
]


def equipment(
    id: str,
    type: str = "Projector",
    qty: int = 10,
    home: str = "Store Room B",
    status: str = "AVAILABLE",
) -> dict[str, Any]:
    return {
        "id": id,
        "type": type,
        "description": None,
        "total_owned_quantity": qty,
        "home_location": home,
        "operational_status": status,
    }


def requirement(id: str, event: str, type: str, qty: int) -> dict[str, Any]:
    return {
        "id": id,
        "event_request_id": event,
        "equipment_type": type,
        "quantity": qty,
        "technical_requirements": None,
        "status": "requested",
        "support_note": None,
        "event_name": "Annual Gala" if event == E1 else "Other Event",
        "event_date_times": ["2026-10-14T09:00:00+08:00"],
        "recorded_by": C1,
        "recorded_at": "2026-10-06T09:00:00+08:00",
        "updated_by": None,
        "updated_at": None,
    }


def reservation(
    equipment_id: str,
    qty: int,
    collect: str,
    ret: str,
    *,
    requirement_id: str = REQB,
    event: str = E2,
    created_at: str = "2026-10-07T09:00:00+08:00",
) -> dict[str, Any]:
    """``R(row, qty, collect -> return)``; for E2 / REQB unless stated."""
    return {
        "id": str(uuid.uuid4()),
        "requirement_id": requirement_id,
        "event_request_id": event,
        "equipment_id": equipment_id,
        "quantity": qty,
        "collection_date": collect,
        "return_date": ret,
        "created_by": TSS,
        "created_at": created_at,
    }


def api_error(code: str) -> APIError:
    return APIError(
        {"message": f"database said {code}", "code": code, "details": None,
         "hint": None}
    )


class _Response:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: ReservationStore, table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._orders: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._single = False
        self._write: tuple[str, Any] | None = None

    def select(self, *_columns: str, **_kwargs: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self._filters.append((column, "eq", value))
        return self

    def neq(self, column: str, value: Any) -> _Query:
        self._filters.append((column, "neq", value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self._filters.append((column, "in", list(values)))
        return self

    def lte(self, column: str, value: Any) -> _Query:
        self._filters.append((column, "lte", value))
        return self

    def gte(self, column: str, value: Any) -> _Query:
        self._filters.append((column, "gte", value))
        return self

    def order(self, column: str, desc: bool = False, **_kwargs: Any) -> _Query:
        self._orders.append((column, desc))
        return self

    def limit(self, count: int) -> _Query:
        self._limit = count
        return self

    def single(self) -> _Query:
        self._single = True
        return self

    def maybe_single(self) -> _Query:
        self._single = True
        return self

    def insert(self, payload: Any) -> _Query:
        self._write = ("insert", payload)
        return self

    def update(self, payload: Any) -> _Query:
        self._write = ("update", payload)
        return self

    def delete(self) -> _Query:
        self._write = ("delete", None)
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        for column, op, value in self._filters:
            have = row.get(column)
            if op == "eq" and str(have) != str(value):
                return False
            if op == "neq" and str(have) == str(value):
                return False
            if op == "in" and str(have) not in {str(v) for v in value}:
                return False
            # ISO dates compare correctly as strings.
            if op == "lte" and not str(have) <= str(value):
                return False
            if op == "gte" and not str(have) >= str(value):
                return False
        return True

    def execute(self) -> _Response:
        self._store.queries.append(
            {"table": self._table, "filters": list(self._filters),
             "orders": list(self._orders), "write": self._write}
        )
        error = self._store.errors.get(self._table)
        if error is not None:
            raise error
        if self._write is not None:
            # The reservation path must write only through reserve_equipment.
            self._store.writes.append((self._table, self._write))
            return _Response([])
        rows = [
            dict(r) for r in self._store.rows.get(self._table, [])
            if self._matches(r)
        ]
        for column, desc in reversed(self._orders):
            rows.sort(key=lambda r, c=column: str(r.get(c)), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return _Response(rows[0] if rows else None)
        return _Response(rows)


class _RpcCall:
    def __init__(self, store: ReservationStore, name: str, params: dict) -> None:
        self._store = store
        self._name = name
        self._params = params

    def execute(self) -> _Response:
        if self._store.rpc_error is not None:
            raise self._store.rpc_error
        if self._store.rpc_result is not None:
            return _Response(self._store.rpc_result)
        assert self._name == "reserve_equipment", f"unexpected rpc {self._name}"
        p = self._params
        req = next(
            r for r in self._store.rows["equipment_requirements"]
            if r["id"] == p["p_requirement_id"]
        )
        row = {
            "id": str(uuid.uuid4()),
            "requirement_id": p["p_requirement_id"],
            "event_request_id": req["event_request_id"],
            "equipment_id": p["p_equipment_id"],
            "quantity": p["p_quantity"],
            "collection_date": p["p_collection_date"],
            "return_date": p["p_return_date"],
            "created_by": p["p_created_by"],
            "created_at": "2026-10-12T10:00:00+08:00",
        }
        self._store.rows["equipment_reservations"].append(row)
        return _Response(row)


class ReservationStore:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {
            "equipment": [
                equipment(P10),
                equipment(PX, qty=6, home="Store Room C"),
                equipment(PH10, home="Harbour Room"),
                equipment(PS10, home="Search Small Room"),
                equipment(S4, type="Speaker", qty=4),
            ],
            "equipment_requirements": [
                requirement(REQ1, E1, "Projector", 5),
                requirement(REQ2, E1, "Speaker", 2),
                requirement(REQ3, E1, "Projector", 3),
                requirement(REQB, E2, "Projector", 10),
            ],
            "equipment_reservations": [],
        }
        self.queries: list[dict[str, Any]] = []
        self.writes: list[tuple[str, Any]] = []
        self.errors: dict[str, Exception] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_result: Any = None
        self.rpc_error: Exception | None = None

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> _RpcCall:
        self.rpc_calls.append((name, dict(params)))
        return _RpcCall(self, name, dict(params))

    # --- helpers ------------------------------------------------------------

    def add_equipment(self, row: dict[str, Any]) -> None:
        self.rows["equipment"].append(row)

    def reserve(self, *rows: dict[str, Any]) -> None:
        self.rows["equipment_reservations"].extend(rows)

    def reservations(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows["equipment_reservations"]]

    def requirements(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows["equipment_requirements"]]

    def reservation_queries(self) -> list[dict[str, Any]]:
        return [q for q in self.queries if q["table"] == "equipment_reservations"]


class Services:
    """Stubs authService ``/auth/me`` and venueService ``GET /venues/locations``.

    Role-blind: it answers whatever the caller's role (F2). venueService's
    real role check is covered by ``test_venue_contract.py``.
    """

    def __init__(self) -> None:
        self.roles = ["technical_support"]
        self.user_id = TSS
        self.venues_response = httpx.Response(200, json=VENUES_JSON)
        self.venues_error: Exception | None = None
        self.calls: list[str] = []

    def get(self, url: Any, *args: Any, **kwargs: Any) -> httpx.Response:
        url = str(url)
        self.calls.append(url)
        if url.endswith("/auth/me"):
            return httpx.Response(
                200,
                json={"id": self.user_id, "role": self.roles[0], "roles": self.roles},
            )
        if url.rstrip("/").endswith("/venues/locations"):
            if self.venues_error is not None:
                raise self.venues_error
            return self.venues_response
        raise AssertionError(f"unexpected GET {url}")

    @property
    def venue_calls(self) -> list[str]:
        return [
            c for c in self.calls if c.rstrip("/").endswith("/venues/locations")
        ]
