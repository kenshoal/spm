from app.models.event_request import (
    EventRequestResponse,
    EventRequestStatus,
    EventReviewDecision,
)
from app.repositories.event_request_repository import EventRequestRpcError
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)
from app.services.notification_client import NotificationClient

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


class DecisionReasonRequiredError(Exception):
    """A returned or rejected request must explain what the organiser needs to know."""

    def __init__(self, decision: EventRequestStatus) -> None:
        super().__init__(f"A reason is required when the decision is {decision.value}")


class EventTransitionService:
    """Own coordinator transitions and SCRUM-17 review decisions.

    Every operation uses a database function that locks the request and
    re-checks the latest assignment before writing. Planning/confirmation and
    post-submission change requests remain in their owning stories.
    """

    def __init__(
        self,
        event_request_service: EventRequestService,
        notification_client: NotificationClient | None = None,
    ) -> None:
        self.event_request_service = event_request_service
        self.notification_client = notification_client or NotificationClient(None)

    def start_review(
        self, event_request_id: str, caller_id: str
    ) -> EventRequestResponse:
        return self._advance(
            event_request_id, caller_id, EventRequestStatus.UNDER_REVIEW
        )

    def resume_review(
        self, event_request_id: str, caller_id: str
    ) -> EventRequestResponse:
        try:
            return self.event_request_service.resume_review_by_coordinator(
                event_request_id, caller_id
            )
        except EventRequestRpcError as error:
            if error.errcode == NOT_FOUND_ERRCODE:
                raise EventRequestNotFoundError(event_request_id) from error
            if error.errcode == NOT_ASSIGNED_ERRCODE:
                raise TransitionForbiddenError(event_request_id) from error
            if error.errcode == NOT_ALLOWED_ERRCODE:
                raise TransitionNotAllowedError(
                    event_request_id,
                    "A clarification response is required before review can continue",
                ) from error
            raise

    def cancel(self, event_request_id: str, caller_id: str) -> EventRequestResponse:
        return self._advance(
            event_request_id, caller_id, EventRequestStatus.CANCELLED
        )

    def complete(self, event_request_id: str, caller_id: str) -> EventRequestResponse:
        return self._advance(
            event_request_id, caller_id, EventRequestStatus.COMPLETED
        )

    def decide(
        self,
        event_request_id: str,
        caller_id: str,
        payload: EventReviewDecision,
    ) -> EventRequestResponse:
        if payload.requires_reason() and payload.reason is None:
            raise DecisionReasonRequiredError(payload.decision)
        try:
            event_request = self.event_request_service.decide_by_coordinator(
                event_request_id,
                caller_id,
                payload.decision,
                payload.reason,
            )
        except EventRequestRpcError as error:
            if error.errcode == NOT_FOUND_ERRCODE:
                raise EventRequestNotFoundError(event_request_id) from error
            if error.errcode == NOT_ASSIGNED_ERRCODE:
                raise TransitionForbiddenError(event_request_id) from error
            if error.errcode == NOT_ALLOWED_ERRCODE:
                raise TransitionNotAllowedError(
                    event_request_id,
                    f"Cannot decide event request {event_request_id} from its current status",
                ) from error
            raise

        # Only after the locked write succeeded, so a refused decision tells nobody
        # to clarify something that was never recorded. Approved and Rejected
        # notices belong to SCRUM-36. A reason is guaranteed here: the check above
        # refuses a Changes Requested decision without one.
        if payload.decision == EventRequestStatus.CHANGES_REQUESTED:
            self.notification_client.notify_clarification_requested(
                event_request_id=event_request_id,
                organiser_id=event_request.organiser_id,
                reason=payload.reason,
            )
        return event_request

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
