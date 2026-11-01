"""Shared fakes and data for the SCRUM-33 equipment-requirement tests.

Imported as ``requirements_support`` (not ``tests.requirements_support``):
CI runs plain ``pytest``, which puts this folder, not the repo, on sys.path.

* ``RequirementsStore`` stands in for the Supabase client. Unlike the
  conftest ``FakeSupabase`` it applies ``eq``/``neq``/``order``/``limit`` to the
  rows it holds and keeps what is inserted, so a router that forgets a filter
  or an ordering returns the wrong rows and the test fails.
* ``FakeEventService`` stands in for eventRequestService behind an
  ``httpx.MockTransport``; the real ``EventRequestClient`` runs on top of it.
* The fixtures that wire these into the app (``req_store``, ``req_events``,
  ``req_api``, ``as_user``) live in conftest.py.

Case IDs trace to docs/testcases/scrum_33_testcases.md.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from postgrest.exceptions import APIError

from app.event_requests_client import EventRequestClient

C1 = "11111111-1111-1111-1111-111111111111"  # Coordinator assigned to E1
C2 = "22222222-2222-2222-2222-222222222222"  # another Coordinator
TSS = "33333333-3333-3333-3333-333333333333"  # Technical Support Staff
ORGANISER = "44444444-4444-4444-4444-444444444444"
MANAGER = "55555555-5555-5555-5555-555555555555"
E1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
E2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
MISSING = "99999999-9999-4999-8999-999999999999"
EVENT_URL = "http://events.test"
GALA_DATES = ["2027-03-15T09:00:00+08:00"]

CATALOGUE: list[dict[str, Any]] = [
    {"id": "e0000000-0000-4000-8000-000000000001", "type": "Projector",
     "operational_status": "AVAILABLE", "total_owned_quantity": 10,
     "home_location": "Store Room B"},
    {"id": "e0000000-0000-4000-8000-000000000002", "type": "Wireless Microphone",
     "operational_status": "DAMAGED", "total_owned_quantity": 4,
     "home_location": "Store Room B"},
    {"id": "e0000000-0000-4000-8000-000000000003", "type": "Fog Machine",
     "operational_status": "RETIRED", "total_owned_quantity": 2,
     "home_location": "Store Room C"},
]


def requirement_row(**overrides: Any) -> dict[str, Any]:
    """A stored equipment_requirements row as the Data API returns it."""
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "event_request_id": E1,
        "equipment_type": "Projector",
        "quantity": 2,
        "technical_requirements": "HDMI, 4K",
        "status": "requested",
        "support_note": None,
        "event_name": "Annual Gala",
        "event_date_times": list(GALA_DATES),
        "recorded_by": C1,
        "recorded_at": "2026-10-06T09:00:00+08:00",
        "updated_by": None,
        "updated_at": None,
        "essential": True,
        "essential_note": None,
    }
    row.update(overrides)
    return row


def api_error(code: str) -> APIError:
    return APIError({"message": f"database said {code}", "code": code,
                     "details": None, "hint": None})


class _Response:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: RequirementsStore, table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._orders: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._single = False
        self._insert: dict[str, Any] | None = None

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

    def insert(self, payload: dict[str, Any]) -> _Query:
        self._insert = dict(payload)
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
        return True

    def execute(self) -> _Response:
        self._store.queries.append(
            {"table": self._table, "filters": list(self._filters),
             "orders": list(self._orders), "insert": self._insert}
        )
        error = self._store.errors.get(self._table)
        if error is not None:
            raise error
        if self._insert is not None:
            self._store.inserts.append((self._table, dict(self._insert)))
            row = {**requirement_row(), "technical_requirements": None,
                   "event_name": None, "event_date_times": [],
                   "recorded_at": "2026-10-06T12:00:00+08:00",
                   **self._insert}
            row["id"] = str(uuid.uuid4())
            row["status"] = "requested"
            row["support_note"] = row["updated_by"] = row["updated_at"] = None
            self._store.rows.setdefault(self._table, []).append(row)
            return _Response([row])
        rows = [r for r in self._store.rows.get(self._table, []) if self._matches(r)]
        for column, desc in reversed(self._orders):
            rows.sort(key=lambda r, c=column: str(r.get(c)), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return _Response(rows[0] if rows else None)
        return _Response(rows)


class _RpcCall:
    def __init__(self, store: RequirementsStore) -> None:
        self._store = store

    def execute(self) -> _Response:
        if self._store.rpc_error is not None:
            raise self._store.rpc_error
        return _Response(self._store.rpc_result)


class RequirementsStore:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {
            "equipment": [dict(r) for r in CATALOGUE],
            "equipment_requirements": [],
        }
        self.inserts: list[tuple[str, dict[str, Any]]] = []
        self.queries: list[dict[str, Any]] = []
        self.errors: dict[str, Exception] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_result: Any = None
        self.rpc_error: Exception | None = None

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> _RpcCall:
        self.rpc_calls.append((name, dict(params)))
        return _RpcCall(self)

    def requirement_queries(self) -> list[dict[str, Any]]:
        return [q for q in self.queries if q["table"] == "equipment_requirements"]

    def nothing_stored(self) -> bool:
        return not self.inserts and not self.rpc_calls


class FakeEventService:
    """eventRequestService as seen through its HTTP API."""

    def __init__(self) -> None:
        self.coordinator_id: str = C1
        self.event: dict[str, Any] = {
            "id": E1,
            "organiser_id": ORGANISER,
            "status": "Under Review",
            "event_name": "Annual Gala",
            "proposed_date_times": list(GALA_DATES),
            "equipment_requirements": "Organiser note: projector",
        }
        self.coordinator_reply: httpx.Response | None = None
        self.event_reply: httpx.Response | None = None
        self.error: Exception | None = None
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if request.url.path.endswith("/coordinator"):
            if self.coordinator_reply is not None:
                return self.coordinator_reply
            return httpx.Response(200, json={
                "id": 7, "event_request_id": self.event["id"],
                "coordinator_id": self.coordinator_id, "assigned_by": MANAGER,
                "assigned_at": "2026-10-01T10:00:00+08:00",
            })
        if self.event_reply is not None:
            return self.event_reply
        return httpx.Response(200, json=self.event)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    def client(self) -> EventRequestClient:
        return EventRequestClient(EVENT_URL, transport=httpx.MockTransport(self.handler))


def bearer(token: str = "test-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
