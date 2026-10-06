from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.controllers import event_request_controller
from app.main import create_app
from app.repositories import EventRequestRpcError, SupabaseRepositoryError

# The statuses a coordinator may cancel from: every non-terminal status
# except Draft, which carries no assignment (mirrors migration 0012).
CANCEL_SOURCE_STATUSES = {
    "Submitted",
    "Under Review",
    "Changes Requested",
    "Approved",
    "Planning",
    "Confirmed",
}


class FakeEventRequestRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.coordinator_assignment_rows: list[dict[str, Any]] = []
        self.review_decision_rows: list[dict[str, Any]] = []
        self.change_request_rows: list[dict[str, Any]] = []

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        now = (datetime.now(UTC) + timedelta(microseconds=len(self.rows))).isoformat()
        row = {
            **values,
            "id": str(uuid4()),
            "created_at": now,
            "updated_at": now,
        }
        self.rows[row["id"]] = row
        return dict(row)

    def list_for_organiser(self, organiser_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in reversed(list(self.rows.values()))
            if row["organiser_id"] == organiser_id
        ]

    def get_organisation_id(self, user_id: str) -> str | None:
        return None  # No memberships; see test_organisation_access.py.

    def list_shared_with_organisation(
        self, organisation_id: str
    ) -> list[dict[str, Any]]:
        return []

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in reversed(list(self.rows.values()))
            if row["status"] == status
        ]

    def get_for_organiser(
        self, event_request_id: str, organiser_id: str
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if row is None or row["organiser_id"] != organiser_id:
            return None
        return dict(row)

    def update_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return None
        row.update(values)
        row["updated_at"] = datetime.now(UTC).isoformat()
        return dict(row)

    def submit_for_organiser(
        self,
        event_request_id: str,
        organiser_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return None
        row.update(values)
        row["status"] = "Submitted"
        row["updated_at"] = datetime.now(UTC).isoformat()
        return dict(row)

    def delete_for_organiser(self, event_request_id: str, organiser_id: str) -> bool:
        row = self.rows.get(event_request_id)
        if (
            row is None
            or row["organiser_id"] != organiser_id
            or row["status"] != "Draft"
        ):
            return False
        del self.rows[event_request_id]
        return True

    def get_by_id(self, event_request_id: str) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        return dict(row) if row is not None else None

    def get_by_ids(self, event_request_ids: list[str]) -> list[dict[str, Any]]:
        wanted = set(event_request_ids)
        rows = [row for row in self.rows.values() if row["id"] in wanted]
        return [
            dict(row)
            for row in sorted(rows, key=lambda r: r["created_at"], reverse=True)
        ]

    def update_status(
        self, event_request_id: str, from_status: str, to_status: str
    ) -> dict[str, Any] | None:
        row = self.rows.get(event_request_id)
        if row is None or row["status"] != from_status:
            return None
        row["status"] = to_status
        return dict(row)

    def advance_by_coordinator(
        self, event_request_id: str, coordinator_id: str, to_status: str
    ) -> dict[str, Any]:
        """Mirrors the advance_event_request_by_coordinator RPC: not found,
        latest-assignment and transition checks happen before any write, so
        a refused transition leaves the row untouched."""
        row = self.rows.get(event_request_id)
        if row is None:
            raise EventRequestRpcError("not found", errcode="P0002")

        assignments = [
            assignment
            for assignment in self.coordinator_assignment_rows
            if assignment["event_request_id"] == event_request_id
        ]
        latest = max(assignments, key=lambda assignment: assignment["id"], default=None)
        if latest is None or latest["coordinator_id"] != coordinator_id:
            raise EventRequestRpcError("not assigned", errcode="P0003")

        allowed = (
            (to_status == "Under Review" and row["status"] == "Submitted")
            or (to_status == "Completed" and row["status"] == "Confirmed")
            or (
                to_status == "Cancelled"
                and row["status"] in CANCEL_SOURCE_STATUSES
            )
        )
        if not allowed:
            raise EventRequestRpcError("not allowed", errcode="P0004")

        row["status"] = to_status
        row["updated_at"] = datetime.now(UTC).isoformat()
        return dict(row)

    def decide_by_coordinator(
        self,
        event_request_id: str,
        coordinator_id: str,
        decision: str,
        reason: str | None,
    ) -> dict[str, Any]:
        """Mirror the atomic review-decision RPC for API behavior tests."""
        row = self.rows.get(event_request_id)
        if row is None:
            raise EventRequestRpcError("not found", errcode="P0002")

        assignments = [
            assignment
            for assignment in self.coordinator_assignment_rows
            if assignment["event_request_id"] == event_request_id
        ]
        latest = max(assignments, key=lambda assignment: assignment["id"], default=None)
        if latest is None or latest["coordinator_id"] != coordinator_id:
            raise EventRequestRpcError("not assigned", errcode="P0003")
        if row["status"] != "Under Review" or decision not in {
            "Changes Requested",
            "Approved",
            "Rejected",
        }:
            raise EventRequestRpcError("not allowed", errcode="P0004")

        self.review_decision_rows.append(
            {
                "id": len(self.review_decision_rows) + 1,
                "event_request_id": event_request_id,
                "coordinator_id": coordinator_id,
                "decision_status": decision,
                "reason": reason,
                "decided_at": datetime.now(UTC).isoformat(),
                "organiser_response": None,
                "responded_at": None,
            }
        )
        row["status"] = decision
        row["updated_at"] = datetime.now(UTC).isoformat()
        return dict(row)

    def list_review_decisions(
        self, event_request_id: str
    ) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in reversed(self.review_decision_rows)
            if row["event_request_id"] == event_request_id
        ]

    def create_change_request(
        self,
        event_request_id: str,
        organiser_id: str,
        explanation: str,
        proposed_changes: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.rows.get(event_request_id)
        if row is None or row["organiser_id"] != organiser_id:
            raise EventRequestRpcError("Event request not found", "P0002")
        if row["status"] not in {"Approved", "Planning"}:
            raise EventRequestRpcError("Change request not allowed", "P0004")
        if any(
            item["event_request_id"] == event_request_id and item["status"] == "Pending"
            for item in self.change_request_rows
        ):
            raise EventRequestRpcError("Pending change request exists", "P0004")
        if all(row.get(key) == value for key, value in proposed_changes.items()):
            raise EventRequestRpcError("No value changed", "P0004")
        now = datetime.now(UTC).isoformat()
        change = {
            "id": str(uuid4()),
            "event_request_id": event_request_id,
            "organiser_id": organiser_id,
            "status": "Pending",
            "explanation": explanation,
            "proposed_changes": deepcopy(proposed_changes),
            "base_event_updated_at": row["updated_at"],
            "coordinator_id": None,
            "decision_reason": None,
            "created_at": now,
            "decided_at": None,
        }
        self.change_request_rows.append(change)
        return deepcopy(change)

    def list_change_requests(self, event_request_id: str) -> list[dict[str, Any]]:
        return [
            deepcopy(row)
            for row in reversed(self.change_request_rows)
            if row["event_request_id"] == event_request_id
        ]

    def decide_change_request(
        self,
        event_request_id: str,
        change_request_id: str,
        coordinator_id: str,
        decision: str,
        reason: str | None,
    ) -> dict[str, Any]:
        event = self.rows.get(event_request_id)
        change = next(
            (row for row in self.change_request_rows if row["id"] == change_request_id),
            None,
        )
        if event is None or change is None or change["event_request_id"] != event_request_id:
            raise EventRequestRpcError("Change request not found", "P0002")
        assignments = [
            row for row in self.coordinator_assignment_rows
            if row["event_request_id"] == event_request_id
        ]
        if not assignments or assignments[-1]["coordinator_id"] != coordinator_id:
            raise EventRequestRpcError("Not assigned", "P0003")
        if change["status"] != "Pending" or event["updated_at"] != change["base_event_updated_at"]:
            raise EventRequestRpcError("Change request is stale", "P0004")
        if decision == "Approved":
            event.update(deepcopy(change["proposed_changes"]))
            event["updated_at"] = datetime.now(UTC).isoformat()
        change.update(
            {
                "status": decision,
                "coordinator_id": coordinator_id,
                "decision_reason": reason,
                "decided_at": datetime.now(UTC).isoformat(),
            }
        )
        return deepcopy(change)

    def respond_to_clarification(
        self, event_request_id: str, organiser_id: str, response: str
    ) -> dict[str, Any]:
        request = self.rows.get(event_request_id)
        if request is None or request["organiser_id"] != organiser_id:
            raise EventRequestRpcError("not found", errcode="P0002")
        decisions = [
            row
            for row in self.review_decision_rows
            if row["event_request_id"] == event_request_id
            and row["decision_status"] == "Changes Requested"
        ]
        latest = decisions[-1] if decisions else None
        if (
            request["status"] != "Changes Requested"
            or latest is None
            or latest["organiser_response"] is not None
            or not response.strip()
        ):
            raise EventRequestRpcError("not allowed", errcode="P0004")
        latest["organiser_response"] = response.strip()
        latest["responded_at"] = datetime.now(UTC).isoformat()
        return dict(latest)

    def resume_review_by_coordinator(
        self, event_request_id: str, coordinator_id: str
    ) -> dict[str, Any]:
        request = self.rows.get(event_request_id)
        if request is None:
            raise EventRequestRpcError("not found", errcode="P0002")
        assignments = [
            row for row in self.coordinator_assignment_rows
            if row["event_request_id"] == event_request_id
        ]
        latest_assignment = assignments[-1] if assignments else None
        if latest_assignment is None or latest_assignment["coordinator_id"] != coordinator_id:
            raise EventRequestRpcError("not assigned", errcode="P0003")
        decisions = [
            row for row in self.review_decision_rows
            if row["event_request_id"] == event_request_id
            and row["decision_status"] == "Changes Requested"
        ]
        latest_decision = decisions[-1] if decisions else None
        if (
            request["status"] != "Changes Requested"
            or latest_decision is None
            or latest_decision["organiser_response"] is None
        ):
            raise EventRequestRpcError("not allowed", errcode="P0004")
        request["status"] = "Under Review"
        request["updated_at"] = datetime.now(UTC).isoformat()
        return dict(request)


class FakeCoordinatorAssignmentRepository:
    def __init__(
        self, event_requests: FakeEventRequestRepository | None = None
    ) -> None:
        # Sharing the assignment rows with the event-request fake lets its
        # advance_by_coordinator see the same assignments the RPC would.
        self.rows: list[dict[str, Any]] = (
            event_requests.coordinator_assignment_rows
            if event_requests is not None
            else []
        )

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        row = {
            **values,
            "id": len(self.rows) + 1,
            "assigned_at": datetime.now(UTC).isoformat(),
        }
        self.rows.append(row)
        return dict(row)

    def latest_for_event_request(
        self, event_request_id: str
    ) -> dict[str, Any] | None:
        matches = [r for r in self.rows if r["event_request_id"] == event_request_id]
        return dict(matches[-1]) if matches else None

    def assigned_event_request_ids(self, event_request_ids: list[str]) -> set[str]:
        wanted = set(event_request_ids)
        return {r["event_request_id"] for r in self.rows} & wanted

    def list_for_coordinator(self, coordinator_id: str) -> list[dict[str, Any]]:
        return [
            dict(row) for row in self.rows if row["coordinator_id"] == coordinator_id
        ]

    def list_for_event_requests(
        self, event_request_ids: list[str]
    ) -> list[dict[str, Any]]:
        wanted = set(event_request_ids)
        return [dict(row) for row in self.rows if row["event_request_id"] in wanted]


def submit_event_request(repository: FakeEventRequestRepository) -> str:
    row = repository.create(
        {
            "organiser_id": "organiser-1",
            "status": "Submitted",
            "event_name": "Community Dinner",
        }
    )
    return row["id"]


ORGANISER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ORGANISER_ID = "22222222-2222-4222-8222-222222222222"


def make_client(
    repository: FakeEventRequestRepository | None = None,
    organiser_id: str = ORGANISER_ID,
) -> TestClient:
    application = create_app(repository or FakeEventRequestRepository())
    application.dependency_overrides[event_request_controller.get_organiser_id] = (
        lambda: organiser_id
    )
    application.dependency_overrides[event_request_controller.get_coordinator_id] = (
        lambda: organiser_id
    )
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: event_request_controller.AuthenticatedCaller(
        id=organiser_id, roles=("event_organiser",)
    )
    return TestClient(application)


def make_coordinator_client(
    event_requests: FakeEventRequestRepository,
    coordinators: FakeCoordinatorAssignmentRepository,
    coordinator_id: str,
) -> TestClient:
    application = create_app(event_requests, coordinators)
    application.dependency_overrides[event_request_controller.get_coordinator_id] = (
        lambda: coordinator_id
    )
    return TestClient(application)


def complete_payload() -> dict[str, object]:
    return {
        "event_name": "Community Technology Workshop",
        "purpose": "Teach practical skills",
        "description": "A hands-on community programme",
        "proposed_date_times": ["2026-10-20T10:00:00+08:00"],
        "expected_attendance": 80,
        "venue_requirements": "Classroom with movable tables",
        "accessibility_needs": "No special requirements",
        "equipment_requirements": "Projector and two microphones",
        "registration_needs": "Online registration and check-in desk",
    }


# Purpose: Confirms the service exposes a basic readiness signal.
def test_health() -> None:
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "eventRequestService",
        "status": "ok",
    }


# Purpose: Proves an organiser can save and retrieve an intentionally incomplete draft.
def test_create_and_get_incomplete_draft() -> None:
    with make_client() as client:
        created = client.post(
            "/event-requests",
            json={"event_name": "Community Dinner"},
        )
        fetched = client.get(f"/event-requests/{created.json()['id']}")

    assert created.status_code == 201
    assert created.json()["status"] == "Draft"
    assert created.json()["organiser_id"] == ORGANISER_ID
    assert created.json()["purpose"] is None
    assert fetched.json() == created.json()


# Purpose: Proves every event-request field survives a draft round trip unchanged.
def test_all_draft_fields_round_trip_unchanged() -> None:
    payload = complete_payload()
    with make_client() as client:
        created = client.post("/event-requests", json=payload)
        fetched = client.get(f"/event-requests/{created.json()['id']}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    for field, value in payload.items():
        if field == "proposed_date_times":
            assert len(created.json()[field]) == len(value)  # type: ignore[arg-type]
        else:
            assert created.json()[field] == value


# Purpose: Protects request privacy by excluding records owned by another organiser.
def test_list_returns_only_the_current_organisers_requests() -> None:
    repository = FakeEventRequestRepository()
    repository.create(
        {"organiser_id": ORGANISER_ID, "status": "Draft", "event_name": "Visible"}
    )
    repository.create(
        {
            "organiser_id": OTHER_ORGANISER_ID,
            "status": "Draft",
            "event_name": "Hidden",
        }
    )

    with make_client(repository) as client:
        response = client.get("/event-requests")

    assert response.status_code == 200
    assert [item["event_name"] for item in response.json()] == ["Visible"]


# Purpose: Proves reopening a draft updates the same record and supports clearing fields.
def test_patch_updates_the_same_draft_and_can_clear_a_field() -> None:
    with make_client() as client:
        created = client.post(
            "/event-requests",
            json={"event_name": "Original", "purpose": "Initial purpose"},
        ).json()
        response = client.patch(
            f"/event-requests/{created['id']}",
            json={"event_name": "Updated", "purpose": ""},
        )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["event_name"] == "Updated"
    assert response.json()["purpose"] is None


# Purpose: Confirms an organiser can discard a Draft and cannot retrieve it afterwards.
def test_delete_removes_the_draft() -> None:
    with make_client() as client:
        created = client.post("/event-requests", json={}).json()
        deleted = client.delete(f"/event-requests/{created['id']}")
        fetched = client.get(f"/event-requests/{created['id']}")

    assert deleted.status_code == 204
    assert fetched.status_code == 404


# Purpose: Prevents one organiser from reading or mutating another organiser's Draft.
def test_other_organiser_cannot_read_update_or_delete() -> None:
    repository = FakeEventRequestRepository()
    created = repository.create(
        {
            "organiser_id": OTHER_ORGANISER_ID,
            "status": "Draft",
            "event_name": "Private draft",
        }
    )
    path = f"/event-requests/{created['id']}"

    with make_client(repository) as client:
        fetched = client.get(path)
        updated = client.patch(path, json={"event_name": "Changed"})
        deleted = client.delete(path)

    assert fetched.status_code == 404
    assert updated.status_code == 404
    assert deleted.status_code == 404
    assert repository.rows[created["id"]]["event_name"] == "Private draft"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/event-requests"),
        ("GET", "/event-requests/assigned-to-me"),
        ("GET", "/event-requests/public-events"),
        ("POST", "/event-requests"),
        ("POST", "/event-requests/submissions"),
        ("GET", "/event-requests/00000000-0000-0000-0000-000000000001"),
        ("PATCH", "/event-requests/00000000-0000-0000-0000-000000000001"),
        ("POST", "/event-requests/00000000-0000-0000-0000-000000000001/submit"),
        ("DELETE", "/event-requests/00000000-0000-0000-0000-000000000001"),
    ],
)
# Purpose: Ensures every event-request operation rejects a missing bearer session.
def test_every_operation_rejects_unauthenticated_requests(
    method: str, path: str
) -> None:
    with TestClient(create_app(FakeEventRequestRepository())) as client:
        response = client.request(
            method,
            path,
            json={} if method in {"POST", "PATCH"} else None,
        )

    assert response.status_code == 401


# Purpose: Refuses an organiser identity supplied by the browser instead of a session.
def test_organiser_header_cannot_bypass_authentication() -> None:
    with TestClient(create_app(FakeEventRequestRepository())) as client:
        response = client.get(
            "/event-requests",
            headers={"X-Organiser-Id": "attacker"},
        )

    assert response.status_code == 401


# Purpose: Binds stored ownership to the identity verified by authService.
def test_verified_identity_overrides_spoofed_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "id": ORGANISER_ID,
                "role": "event_operations_manager",
                "roles": ["event_operations_manager", "event_organiser"],
            },
        ),
    )
    get_settings.cache_clear()
    try:
        with TestClient(create_app(FakeEventRequestRepository())) as client:
            created = client.post(
                "/event-requests",
                headers={
                    "Authorization": "Bearer valid-token",
                    "X-Organiser-Id": "attacker",
                },
                json={},
            )
    finally:
        get_settings.cache_clear()

    assert created.status_code == 201
    assert created.json()["organiser_id"] == ORGANISER_ID


@pytest.mark.parametrize(
    "roles",
    [["attendee"], ["admin"], ["event_operations_manager"]],
)
# Purpose: Prevents authenticated non-organisers from accessing organiser requests.
def test_event_request_operations_require_organiser_role(
    monkeypatch: pytest.MonkeyPatch,
    roles: list[str],
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"id": ORGANISER_ID, "role": roles[0], "roles": roles},
        ),
    )
    get_settings.cache_clear()
    try:
        with TestClient(create_app(FakeEventRequestRepository())) as client:
            response = client.post(
                "/event-requests/submissions",
                headers={"Authorization": "Bearer valid-token"},
                json=complete_payload(),
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


# Purpose: Rejects invalid or expired sessions before protected data is accessed.
def test_invalid_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(401, json={"detail": "Invalid"}),
    )
    get_settings.cache_clear()
    try:
        with TestClient(create_app(FakeEventRequestRepository())) as client:
            response = client.get(
                "/event-requests",
                headers={"Authorization": "Bearer expired"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401


# Purpose: Prevents invalid attendance from being persisted in a Draft.
def test_rejects_invalid_expected_attendance() -> None:
    with make_client() as client:
        response = client.post(
            "/event-requests",
            json={"expected_attendance": 0},
        )

    assert response.status_code == 422


# Purpose: Proves a complete new form can enter coordination without a prior Draft.
def test_submit_complete_new_event_request_directly() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        response = client.post("/event-requests/submissions", json=complete_payload())

    assert response.status_code == 201
    assert response.json()["status"] == "Submitted"
    assert response.json()["organiser_id"] == ORGANISER_ID
    assert len(repository.rows) == 1


@pytest.mark.parametrize("missing_field", list(complete_payload()))
# Purpose: Prevents any incomplete new form from entering the coordination workflow.
def test_direct_submission_requires_every_form_field(missing_field: str) -> None:
    repository = FakeEventRequestRepository()
    payload = complete_payload()
    payload.pop(missing_field)

    with make_client(repository) as client:
        response = client.post("/event-requests/submissions", json=payload)

    assert response.status_code == 422
    assert repository.rows == {}


# Purpose: Moves the existing Draft to Submitted without creating a duplicate record.
def test_submit_completed_draft() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        created = client.post(
            "/event-requests", json={"event_name": "Initial title"}
        ).json()
        response = client.post(
            f"/event-requests/{created['id']}/submit",
            json=complete_payload(),
        )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["status"] == "Submitted"
    assert response.json()["event_name"] == complete_payload()["event_name"]
    assert len(repository.rows) == 1


# Purpose: Keeps an incomplete saved Draft editable when submission validation fails.
def test_incomplete_draft_remains_draft_after_rejected_submission() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        created = client.post(
            "/event-requests", json={"event_name": "Incomplete"}
        ).json()
        response = client.post(
            f"/event-requests/{created['id']}/submit",
            json={"event_name": "Incomplete"},
        )
        fetched = client.get(f"/event-requests/{created['id']}")

    assert response.status_code == 422
    assert fetched.json()["status"] == "Draft"
    assert fetched.json()["event_name"] == "Incomplete"


# Purpose: Prevents ambiguous local times from being persisted with the wrong offset.
def test_submission_requires_timezone_aware_dates() -> None:
    repository = FakeEventRequestRepository()
    payload = complete_payload()
    payload["proposed_date_times"] = ["2026-10-20T10:00:00"]

    with make_client(repository) as client:
        response = client.post("/event-requests/submissions", json=payload)

    assert response.status_code == 422
    assert repository.rows == {}


# Purpose: Prevents one organiser from submitting another organiser's Draft.
def test_other_organiser_cannot_submit_draft() -> None:
    repository = FakeEventRequestRepository()
    created = repository.create(
        {
            "organiser_id": OTHER_ORGANISER_ID,
            "status": "Draft",
            **complete_payload(),
        }
    )

    with make_client(repository) as client:
        response = client.post(
            f"/event-requests/{created['id']}/submit",
            json=complete_payload(),
        )

    assert response.status_code == 404
    assert repository.rows[created["id"]]["status"] == "Draft"


# Purpose: Prevents resubmission, editing and deletion after coordination begins.
def test_submitted_request_is_read_only() -> None:
    repository = FakeEventRequestRepository()
    with make_client(repository) as client:
        submitted = client.post(
            "/event-requests/submissions", json=complete_payload()
        ).json()
        path = f"/event-requests/{submitted['id']}"
        updated = client.patch(path, json={"event_name": "Changed"})
        resubmitted = client.post(f"{path}/submit", json=complete_payload())
        deleted = client.delete(path)
        fetched = client.get(path)

    assert updated.status_code == 409
    assert resubmitted.status_code == 409
    assert deleted.status_code == 409
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "Submitted"
    assert fetched.json()["event_name"] == complete_payload()["event_name"]


def assign(
    coordinators: FakeCoordinatorAssignmentRepository,
    event_request_id: str,
    coordinator_id: str,
) -> None:
    coordinators.create(
        {
            "event_request_id": event_request_id,
            "coordinator_id": coordinator_id,
            "assigned_by": "ops-1",
        }
    )


# Purpose: A coordinator's assigned-to-me queue lists the requests assigned to them.
def test_assigned_to_me_lists_currently_assigned_requests() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    first = submit_event_request(event_requests)
    second = submit_event_request(event_requests)
    assign(coordinators, first, "coord-1")
    assign(coordinators, second, "coord-1")

    with make_coordinator_client(event_requests, coordinators, "coord-1") as client:
        response = client.get("/event-requests/assigned-to-me")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {first, second}


# Purpose: A reassigned-away coordinator no longer sees the request in their queue.
def test_assigned_to_me_excludes_requests_reassigned_to_someone_else() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    event_request_id = submit_event_request(event_requests)
    assign(coordinators, event_request_id, "coord-1")
    assign(coordinators, event_request_id, "coord-2")

    with make_coordinator_client(event_requests, coordinators, "coord-1") as client:
        response = client.get("/event-requests/assigned-to-me")

    assert response.status_code == 200
    assert response.json() == []


# Purpose: The new coordinator after a reassignment sees the request in their queue.
def test_assigned_to_me_shows_request_to_the_latest_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    event_request_id = submit_event_request(event_requests)
    assign(coordinators, event_request_id, "coord-1")
    assign(coordinators, event_request_id, "coord-2")

    with make_coordinator_client(event_requests, coordinators, "coord-2") as client:
        response = client.get("/event-requests/assigned-to-me")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [event_request_id]


# Purpose: A coordinator with nothing assigned gets an empty queue, not an error.
def test_assigned_to_me_is_empty_when_nothing_is_assigned() -> None:
    with make_coordinator_client(
        FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository(), "coord-1"
    ) as client:
        response = client.get("/event-requests/assigned-to-me")

    assert response.status_code == 200
    assert response.json() == []


# Purpose: Queue results are ordered newest-first like the organiser list.
def test_assigned_to_me_orders_requests_newest_first() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    older = submit_event_request(event_requests)
    newer = submit_event_request(event_requests)
    assign(coordinators, older, "coord-1")
    assign(coordinators, newer, "coord-1")

    with make_coordinator_client(event_requests, coordinators, "coord-1") as client:
        response = client.get("/event-requests/assigned-to-me")

    assert [item["id"] for item in response.json()] == [newer, older]


# Purpose: Queue reads surface a Supabase outage as 502 rather than crashing.
def test_assigned_to_me_maps_repository_failure_to_bad_gateway() -> None:
    class FailingCoordinatorRepository(FakeCoordinatorAssignmentRepository):
        def list_for_coordinator(self, coordinator_id: str) -> list[dict[str, Any]]:
            raise SupabaseRepositoryError("Supabase is down")

    event_requests = FakeEventRequestRepository()
    with make_coordinator_client(
        event_requests, FailingCoordinatorRepository(), "coord-1"
    ) as client:
        response = client.get("/event-requests/assigned-to-me")

    assert response.status_code == 502


@pytest.mark.parametrize(
    "roles",
    [["event_organiser"], ["event_operations_manager"]],
)
# Purpose: Only coordinators may read the assigned-to-me queue (multi-role accepted).
def test_assigned_to_me_requires_coordinator_role(
    monkeypatch: pytest.MonkeyPatch,
    roles: list[str],
) -> None:
    caller_id = str(uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"id": caller_id, "role": roles[0], "roles": roles},
        ),
    )
    get_settings.cache_clear()
    try:
        application = create_app(
            FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository()
        )
        with TestClient(application) as client:
            response = client.get(
                "/event-requests/assigned-to-me",
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


# Purpose: A multi-role account whose roles include Event Coordinator keeps queue access.
def test_assigned_to_me_accepts_multi_role_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller_id = str(uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "id": caller_id,
                "role": "venue_staff",
                "roles": ["venue_staff", "event_coordinator"],
            },
        ),
    )
    get_settings.cache_clear()
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    try:
        application = create_app(event_requests, coordinators)
        event_request_id = submit_event_request(event_requests)
        assign(coordinators, event_request_id, caller_id)
        with TestClient(application) as client:
            response = client.get(
                "/event-requests/assigned-to-me",
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [event_request_id]


@pytest.mark.parametrize(
    ("roles", "relationship", "expected_status"),
    [
        (("event_organiser",), "owner", 200),
        (("event_organiser",), "other", 404),
        (("event_coordinator",), "assigned", 200),
        (("event_coordinator",), "other", 404),
        (("event_operations_manager",), "other", 403),
        (("attendee",), "other", 403),
        (("venue_staff",), "other", 403),
        (("technical_support",), "other", 403),
        (("venue_staff", "event_coordinator"), "assigned", 200),
        (("event_organiser", "event_coordinator"), "owner", 200),
        (("event_organiser", "event_coordinator"), "other", 404),
    ],
)
# AC5-H1 (happy): details are visible only to the owner organiser or the assigned
# coordinator; related-but-unauthorised callers get 404, unrelated roles 403.
def test_get_event_request_is_scoped_to_request_access(
    roles: tuple[str, ...],
    relationship: str,
    expected_status: int,
) -> None:
    caller_id = str(uuid4())
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    application = create_app(event_requests, coordinators)
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: event_request_controller.AuthenticatedCaller(
        id=caller_id, roles=roles
    )

    event_request_id = submit_event_request(event_requests)
    if relationship == "owner":
        event_requests.rows[event_request_id]["organiser_id"] = caller_id
    assign(
        coordinators,
        event_request_id,
        caller_id if relationship == "assigned" else str(uuid4()),
    )

    with TestClient(application) as client:
        response = client.get(
            f"/event-requests/{event_request_id}",
            headers={"Authorization": f"Bearer {caller_id}"},
        )

    assert response.status_code == expected_status


# AC5-N1 (negative): an unassigned coordinator cannot confirm a request exists (404)
def test_coordinator_gets_not_found_for_unassigned_request() -> None:
    event_requests = FakeEventRequestRepository()
    coordinators = FakeCoordinatorAssignmentRepository()
    application = create_app(event_requests, coordinators)
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: event_request_controller.AuthenticatedCaller(
        id="coord-1", roles=("event_coordinator",)
    )
    event_request_id = submit_event_request(event_requests)

    with TestClient(application) as client:
        response = client.get(
            f"/event-requests/{event_request_id}",
            headers={"Authorization": "Bearer coord-1"},
        )

    assert response.status_code == 404


# AC4-H1 (happy): Attendees see only Confirmed or Completed events, public fields only
def test_attendee_view_exposes_only_public_stages_and_fields() -> None:
    repository = FakeEventRequestRepository()
    for event_status in [
        "Draft",
        "Submitted",
        "Under Review",
        "Approved",
        "Planning",
        "Confirmed",
        "Completed",
        "Cancelled",
        "Rejected",
    ]:
        repository.create(
            {
                "organiser_id": OTHER_ORGANISER_ID,
                "status": event_status,
                **complete_payload(),
                "event_name": event_status,
            }
        )
    application = create_app(repository)
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: event_request_controller.AuthenticatedCaller(
        id=str(uuid4()), roles=("attendee",)
    )

    with TestClient(application) as client:
        response = client.get("/event-requests/public-events")

    assert response.status_code == 200
    assert {item["event_name"] for item in response.json()} == {
        "Confirmed",
        "Completed",
    }
    assert all(
        set(item)
        == {
            "id",
            "event_name",
            "description",
            "status",
            "proposed_date_times",
        }
        for item in response.json()
    )


# AC4-N1 (negative): roles other than Attendee are refused the public projection
def test_attendee_view_rejects_unrelated_roles() -> None:
    application = create_app(FakeEventRequestRepository())
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: event_request_controller.AuthenticatedCaller(
        id=str(uuid4()), roles=("event_organiser",)
    )

    with TestClient(application) as client:
        response = client.get("/event-requests/public-events")

    assert response.status_code == 403
