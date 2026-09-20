from app.models.event_request import EventRequestResponse, EventRequestStatus
from app.services.coordinator_assignment_service import (
    CoordinatorAssignmentNotFoundError,
    CoordinatorAssignmentService,
)
from app.services.event_request_service import EventRequestService


class ReviewNotAllowedError(Exception):
    def __init__(self, event_request_id: str, reason: str) -> None:
        super().__init__(reason)
        self.event_request_id = event_request_id


class ReviewForbiddenError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(
            f"Only the assigned Coordinator can start review for "
            f"event request {event_request_id}"
        )
        self.event_request_id = event_request_id


class EventReviewService:
    """Owns the one rule where coordinator assignment and event status meet:
    only the Coordinator currently assigned may start review, and starting
    review is the only thing that moves Submitted -> Under Review.
    Deliberately not a general state machine — that's the rest of
    EventRequestStatus's lifecycle, still to be built (see spm-brain
    backlog C-2); this only implements the one transition this story needs.
    """

    def __init__(
        self,
        event_request_service: EventRequestService,
        coordinator_assignment_service: CoordinatorAssignmentService,
    ) -> None:
        self.event_request_service = event_request_service
        self.coordinator_assignment_service = coordinator_assignment_service

    def start_review(
        self, event_request_id: str, caller_id: str
    ) -> EventRequestResponse:
        event_request = self.event_request_service.get_by_id(event_request_id)

        try:
            assignment = self.coordinator_assignment_service.get_current(
                event_request_id
            )
        except CoordinatorAssignmentNotFoundError as error:
            raise ReviewForbiddenError(event_request_id) from error

        if assignment.coordinator_id != caller_id:
            raise ReviewForbiddenError(event_request_id)

        if event_request.status != EventRequestStatus.SUBMITTED:
            raise ReviewNotAllowedError(
                event_request_id,
                f"Cannot start review from status {event_request.status.value}",
            )

        return self.event_request_service.transition_status(
            event_request_id,
            EventRequestStatus.SUBMITTED,
            EventRequestStatus.UNDER_REVIEW,
        )
