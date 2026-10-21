"""Shared fixtures for the SCRUM-19 API tests.

FakeTechnicalSupportRepository mirrors what the database functions do —
lock the event row, check the latest coordinator, the status, the
requirement's event, suitability, then the one-row-per-staff rule — so the
API tests exercise the service's error mapping against the same refusals
the RPC raises. RecordingNotificationClient captures what the service would
deliver to notificationService.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
)

from app.controllers.event_request_controller import (
    AuthenticatedCaller,
    get_authenticated_caller,
)
from app.main import create_app
from app.repositories.technical_support_repository import (
    EVENT_REQUEST_NOT_FOUND_REASON,
    REQUIREMENT_NOT_FOUND_REASON,
    TechnicalSupportRpcError,
)
from app.services.technical_support_rules import (
    SupportNotAllowedError,
    ensure_support_allowed,
    is_suitable,
)

NOW = datetime(2030, 3, 1, 9, 0, tzinfo=UTC)

COORD = "coord-1"
OTHER_COORD = "coord-2"
TSS_AV = "tss-av"
TSS_AV2 = "tss-av2"
TSS_LIGHT = "tss-light"
TSS_NONE = "tss-none"
VENUE_AV = "venue-av"
ORGANISER = "org-1"
OPS = "ops-1"
ATTENDEE = "att-1"

EVENT = "11111111-1111-4111-8111-111111111111"
OTHER_EVENT = "22222222-2222-4222-8222-222222222222"
REQ_AV = "aaaa0000-0000-4000-8000-000000000001"
REQ_IT = "aaaa0000-0000-4000-8000-000000000002"
REQ_OTHER = "aaaa0000-0000-4000-8000-000000000003"

USER_ROLES: dict[str, tuple[str, ...]] = {
    COORD: ("event_coordinator",),
    OTHER_COORD: ("event_coordinator",),
    TSS_AV: ("technical_support",),
    TSS_AV2: ("technical_support",),
    TSS_LIGHT: ("technical_support",),
    TSS_NONE: ("technical_support",),
    VENUE_AV: ("venue_staff",),
    ORGANISER: ("event_organiser",),
    OPS: ("event_operations_manager",),
    ATTENDEE: ("attendee",),
}

USER_TAGS: dict[str, set[str]] = {
    TSS_AV: {"audio_visual", "it_network"},
    TSS_AV2: {"audio_visual"},
    TSS_LIGHT: {"lighting"},
    VENUE_AV: {"audio_visual"},
}

NOT_ALLOWED = [
    "Draft",
    "Submitted",
    "Under Review",
    "Changes Requested",
    "Rejected",
    "Completed",
    "Cancelled",
]


class FakeTechnicalSupportRepository:
    def __init__(self, event_requests: FakeEventRequestRepository) -> None:
        self.event_requests = event_requests
        self.requirement_rows: list[dict[str, Any]] = []
        self.assignment_rows: list[dict[str, Any]] = []
        self.roles: dict[str, tuple[str, ...]] = dict(USER_ROLES)
        self.tags: dict[str, set[str]] = {k: set(v) for k, v in USER_TAGS.items()}
        self._clock = 0

    # -- writes: the database functions' check order, verbatim ----------
    def _latest_coordinator_id(self, event_request_id: str) -> str | None:
        rows = [
            row
            for row in self.event_requests.coordinator_assignment_rows
            if row["event_request_id"] == event_request_id
        ]
        return max(rows, key=lambda row: row["id"])["coordinator_id"] if rows else None

    def _locked_event(self, event_request_id: str, coordinator_id: str) -> dict:
        event = self.event_requests.rows.get(event_request_id)
        if event is None:
            raise TechnicalSupportRpcError(
                EVENT_REQUEST_NOT_FOUND_REASON,
                "P0002",
                EVENT_REQUEST_NOT_FOUND_REASON,
            )
        if self._latest_coordinator_id(event_request_id) != coordinator_id:
            raise TechnicalSupportRpcError(
                "caller is not the assigned coordinator",
                "P0003",
                "caller is not the assigned coordinator",
            )
        try:
            ensure_support_allowed(event["status"])
        except SupportNotAllowedError:
            raise TechnicalSupportRpcError(
                f"technical support not allowed from status {event['status']}",
                "P0004",
                "technical support not allowed",
            ) from None
        return event

    def record_requirement(self, values: dict[str, Any]) -> dict[str, Any]:
        self._locked_event(values["event_request_id"], values["coordinator_id"])
        self._clock += 1
        row = {
            "id": str(uuid4()),
            "event_request_id": values["event_request_id"],
            "description": values["description"],
            "skill_tag": values["skill_tag"],
            "recorded_by": values["coordinator_id"],
            "recorded_at": NOW + timedelta(minutes=self._clock),
        }
        self.requirement_rows.append(row)
        return dict(row)

    def assign(self, values: dict[str, Any]) -> dict[str, Any]:
        self._locked_event(values["event_request_id"], values["coordinator_id"])
        requirement = next(
            (
                row
                for row in self.requirement_rows
                if row["id"] == values["requirement_id"]
            ),
            None,
        )
        if requirement is None or (
            requirement["event_request_id"] != values["event_request_id"]
        ):
            raise TechnicalSupportRpcError(
                REQUIREMENT_NOT_FOUND_REASON,
                "P0002",
                REQUIREMENT_NOT_FOUND_REASON,
            )
        staff_id = values["staff_id"]
        if not is_suitable(
            self.roles.get(staff_id, ()),
            self.tags.get(staff_id, set()),
            requirement["skill_tag"],
        ):
            raise TechnicalSupportRpcError(
                "staff member is not suitable", "P0005", "staff member is not suitable"
            )
        if any(
            row["requirement_id"] == values["requirement_id"]
            and row["staff_id"] == staff_id
            for row in self.assignment_rows
        ):
            raise TechnicalSupportRpcError(
                "already assigned", "23505", "already assigned"
            )
        self._clock += 1
        row = {
            "id": str(uuid4()),
            "requirement_id": values["requirement_id"],
            "event_request_id": values["event_request_id"],
            "staff_id": staff_id,
            "assigned_by": values["coordinator_id"],
            "assigned_at": NOW + timedelta(minutes=self._clock),
        }
        self.assignment_rows.append(row)
        return dict(row)

    # -- reads ----------------------------------------------------------
    def get_requirement(self, requirement_id: str) -> dict[str, Any] | None:
        row = next(
            (r for r in self.requirement_rows if r["id"] == requirement_id), None
        )
        return dict(row) if row else None

    def list_requirements(self, event_request_id: str) -> list[dict[str, Any]]:
        rows = [
            r for r in self.requirement_rows if r["event_request_id"] == event_request_id
        ]
        return [dict(r) for r in self._ordered(rows, "recorded_at")]

    def list_assignments(self, event_request_id: str) -> list[dict[str, Any]]:
        rows = [
            r for r in self.assignment_rows if r["event_request_id"] == event_request_id
        ]
        return [dict(r) for r in self._ordered(rows, "assigned_at")]

    def list_candidates(self, requirement_id: str) -> list[dict[str, Any]]:
        requirement = self.get_requirement(requirement_id)
        if requirement is None:
            return []
        assigned = {
            row["staff_id"]
            for row in self.assignment_rows
            if row["requirement_id"] == requirement_id
        }
        return [
            {
                "staff_id": staff_id,
                "already_assigned": staff_id in assigned,
            }
            for staff_id in sorted(self.roles)
            if is_suitable(
                self.roles.get(staff_id, ()),
                self.tags.get(staff_id, set()),
                requirement["skill_tag"],
            )
        ]

    @staticmethod
    def _ordered(rows: list[dict[str, Any]], stamp: str) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda row: (row[stamp], row["id"]))


class RecordingNotificationClient:
    """Records technical-support notifications instead of posting them."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    def notify_technical_support_assigned(self, **kwargs: Any) -> None:
        if self.fail:
            raise RuntimeError("notification service down")
        self.calls.append(kwargs)


def seed_event(
    event_requests: FakeEventRequestRepository,
    event_id: str = EVENT,
    status: str = "Planning",
    coordinator_id: str = COORD,
    organiser_id: str = ORGANISER,
) -> None:
    event_requests.rows[event_id] = {
        "id": event_id,
        "organiser_id": organiser_id,
        "status": status,
        "event_name": "Tech Summit 2030",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    event_requests.coordinator_assignment_rows.append(
        {
            "id": len(event_requests.coordinator_assignment_rows) + 1,
            "event_request_id": event_id,
            "coordinator_id": coordinator_id,
            "assigned_by": OPS,
            "assigned_at": NOW.isoformat(),
        }
    )


def seed_requirement(
    repository: FakeTechnicalSupportRepository,
    requirement_id: str = REQ_AV,
    event_id: str = EVENT,
    skill_tag: str = "audio_visual",
    description: str = "Two wireless mics and a mixing-desk operator for the keynote",
) -> None:
    repository.requirement_rows.append(
        {
            "id": requirement_id,
            "event_request_id": event_id,
            "description": description,
            "skill_tag": skill_tag,
            "recorded_by": COORD,
            "recorded_at": NOW.isoformat(),
        }
    )


def make_client(
    event_requests: FakeEventRequestRepository | None = None,
    technical_support: FakeTechnicalSupportRepository | None = None,
    notification: RecordingNotificationClient | None = None,
    caller_id: str = COORD,
    roles: tuple[str, ...] = ("event_coordinator",),
) -> TestClient:
    event_requests = event_requests or FakeEventRequestRepository()
    technical_support = technical_support or FakeTechnicalSupportRepository(
        event_requests
    )
    notification = notification or RecordingNotificationClient()
    application = create_app(
        event_requests,
        FakeCoordinatorAssignmentRepository(event_requests),
        technical_support_repository=technical_support,
        technical_support_notification_client=notification,
    )
    application.dependency_overrides[get_authenticated_caller] = (
        lambda: AuthenticatedCaller(id=caller_id, roles=roles)
    )
    return TestClient(application)


def requirements_path(event_id: str = EVENT) -> str:
    return f"/event-requests/{event_id}/technical-support/requirements"


def technical_support_path(event_id: str = EVENT) -> str:
    return f"/event-requests/{event_id}/technical-support"


def candidates_path(
    event_id: str = EVENT, requirement_id: str = REQ_AV
) -> str:
    return (
        f"/event-requests/{event_id}/technical-support"
        f"/requirements/{requirement_id}/candidates"
    )


def assignments_path(
    event_id: str = EVENT, requirement_id: str = REQ_AV
) -> str:
    return (
        f"/event-requests/{event_id}/technical-support"
        f"/requirements/{requirement_id}/assignments"
    )
