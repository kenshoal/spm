from app.models.coordinator_assignment import (
    CoordinatorAssignmentResponse,
    CoordinatorAssignRequest,
)
from app.models.event_request import EventRequestStatus
from app.repositories.coordinator_assignment_repository import (
    CoordinatorAssignmentRepository,
)
from app.services.event_request_service import EventRequestService

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
    ) -> None:
        self.repository = repository
        self.event_request_service = event_request_service

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
        return CoordinatorAssignmentResponse.model_validate(row)

    def get_current(self, event_request_id: str) -> CoordinatorAssignmentResponse:
        self.event_request_service.get_by_id(event_request_id)
        row = self.repository.latest_for_event_request(event_request_id)
        if row is None:
            raise CoordinatorAssignmentNotFoundError(event_request_id)
        return CoordinatorAssignmentResponse.model_validate(row)
