from app.models.event_request import EventRequestResponse, EventRequestStatus
from app.repositories.event_request_repository import EventRequestRpcError
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)

NOT_FOUND_ERRCODE = "P0002"
NOT_ASSIGNED_ERRCODE = "P0003"
NOT_ALLOWED_ERRCODE = "P0004"


class TransitionNotAllowedError(Exception):
    """The request wasn't in a status the requested transition applies to —
    either the coordinator acted twice or the status moved first."""

    def __init__(self, event_request_id: str, reason: str) -> None:
        super().__init__(reason)
        self.event_request_id = event_request_id


class TransitionForbiddenError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(
            f"Only the Coordinator currently assigned to "
            f"event request {event_request_id} can change its status"
        )
        self.event_request_id = event_request_id


class EventTransitionService:
    """Owns the coordinator status transitions: start review (Submitted ->
    Under Review), cancel (any non-terminal status -> Cancelled) and
    complete (Confirmed -> Completed). Each runs through the
    advance_event_request_by_coordinator database function, which locks the
    row and re-checks the latest assignment in the same transaction — the
    authorization decision and the status write commit atomically.
    Deliberately not a general state machine: approval, rejection and
    changes-requested are owned by other stories (SCRUM-17, SCRUM-35), as
    are planning/confirmation and auto-complete (SCRUM-40).
    """

    def __init__(self, event_request_service: EventRequestService) -> None:
        self.event_request_service = event_request_service

    def start_review(
        self, event_request_id: str, caller_id: str
    ) -> EventRequestResponse:
        return self._advance(
            event_request_id, caller_id, EventRequestStatus.UNDER_REVIEW
        )

    def cancel(self, event_request_id: str, caller_id: str) -> EventRequestResponse:
        return self._advance(
            event_request_id, caller_id, EventRequestStatus.CANCELLED
        )

    def complete(self, event_request_id: str, caller_id: str) -> EventRequestResponse:
        return self._advance(
            event_request_id, caller_id, EventRequestStatus.COMPLETED
        )

    def _advance(
        self,
        event_request_id: str,
        coordinator_id: str,
        to_status: EventRequestStatus,
    ) -> EventRequestResponse:
        try:
            return self.event_request_service.advance_by_coordinator(
                event_request_id, coordinator_id, to_status
            )
        except EventRequestRpcError as error:
            if error.errcode == NOT_FOUND_ERRCODE:
                raise EventRequestNotFoundError(event_request_id) from error
            if error.errcode == NOT_ASSIGNED_ERRCODE:
                raise TransitionForbiddenError(event_request_id) from error
            if error.errcode == NOT_ALLOWED_ERRCODE:
                raise TransitionNotAllowedError(
                    event_request_id,
                    f"Cannot move event request {event_request_id} to "
                    f"{to_status.value} from its current status",
                ) from error
            raise
