from typing import Any

from app.models.coordinator_assignment import (
    CoordinatorAssignmentResponse,
    CoordinatorAssignRequest,
)
from app.models.event_request import EventRequestResponse, EventRequestStatus
from app.repositories.coordinator_assignment_repository import (
    CoordinatorAssignmentRepository,
)
from app.services.event_request_service import EventRequestService
from app.services.notification_client import NotificationClient

_TERMINAL_STATUSES = {
    EventRequestStatus.COMPLETED,
    EventRequestStatus.CANCELLED,
    EventRequestStatus.REJECTED,
}


class CoordinatorAssignmentNotFoundError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(
            f"No Coordinator has been assigned to event request {event_request_id}"
        )
        self.event_request_id = event_request_id


class CoordinatorAssignmentNotAllowedError(Exception):
    def __init__(self, event_request_id: str, reason: str) -> None:
        super().__init__(reason)
        self.event_request_id = event_request_id


class CoordinatorAssignmentService:
    """Owns the coordinator-assignment rule independently of the Supabase
    transport — mirrors EventRequestService's split for the same reason.
    """

    def __init__(
        self,
        repository: CoordinatorAssignmentRepository,
        event_request_service: EventRequestService,
        notification_client: NotificationClient | None = None,
    ) -> None:
        self.repository = repository
        self.event_request_service = event_request_service
        self.notification_client = notification_client or NotificationClient(None)

    def assign(
        self,
        event_request_id: str,
        payload: CoordinatorAssignRequest,
        assigned_by: str,
    ) -> CoordinatorAssignmentResponse:
        event_request = self.event_request_service.get_by_id(event_request_id)

        if event_request.status == EventRequestStatus.DRAFT:
            raise CoordinatorAssignmentNotAllowedError(
                event_request_id,
                "Cannot assign a Coordinator before the request is submitted",
            )
        if event_request.status in _TERMINAL_STATUSES:
            raise CoordinatorAssignmentNotAllowedError(
                event_request_id,
                f"Cannot assign a Coordinator to a {event_request.status.value} request",
            )

        row = self.repository.create(
            {
                "event_request_id": event_request_id,
                "coordinator_id": payload.coordinator_id,
                "assigned_by": assigned_by,
            }
        )
        self.notification_client.notify_coordinator_assigned(
            event_request_id=event_request_id,
            coordinator_id=payload.coordinator_id,
            assigned_by=assigned_by,
        )
        return CoordinatorAssignmentResponse.model_validate(row)

    def list_awaiting_assignment(self) -> list[EventRequestResponse]:
        """Submitted requests nobody is responsible for yet. Assignments are
        append-only and there is no unassign operation, so "has any assignment
        row" is exactly "has a current Coordinator".
        """
        submitted = self.event_request_service.list_by_status(
            EventRequestStatus.SUBMITTED
        )
        if not submitted:
            return []
        assigned = self.repository.assigned_event_request_ids(
            [request.id for request in submitted]
        )
        return [request for request in submitted if request.id not in assigned]

    def get_current(self, event_request_id: str) -> CoordinatorAssignmentResponse:
        self.event_request_service.get_by_id(event_request_id)
        row = self.repository.latest_for_event_request(event_request_id)
        if row is None:
            raise CoordinatorAssignmentNotFoundError(event_request_id)
        return CoordinatorAssignmentResponse.model_validate(row)

    def list_requests_for_coordinator(
        self, coordinator_id: str
    ) -> list[EventRequestResponse]:
        """The requests whose latest assignment is this coordinator — a
        reassigned-away coordinator must not keep seeing the request, so
        "ever assigned" isn't enough; the highest-id assignment decides."""
        mine = self.repository.list_for_coordinator(coordinator_id)
        if not mine:
            return []

        candidates = {row["event_request_id"] for row in mine}
        latest: dict[str, dict[str, Any]] = {}
        for row in self.repository.list_for_event_requests(sorted(candidates)):
            request_id = row["event_request_id"]
            if request_id not in latest or int(row["id"]) > int(
                latest[request_id]["id"]
            ):
                latest[request_id] = row

        assigned_ids = sorted(
            request_id
            for request_id, row in latest.items()
            if row["coordinator_id"] == coordinator_id
        )
        return self.event_request_service.get_by_ids(assigned_ids)
