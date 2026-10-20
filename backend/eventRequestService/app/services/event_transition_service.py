import json
import logging
from typing import Any

from app.models.event_request import (
    EventRequestResponse,
    EventRequestStatus,
    EventReviewDecision,
    SafetyDecision,
)
from app.repositories.event_request_repository import (
    EventRequestRpcError,
    SupabaseRepositoryError,
)
from app.services.event_request_service import (
    EventRequestForbiddenError,
    EventRequestNotFoundError,
    EventRequestService,
)
from app.services.notification_client import NotificationClient

NOT_FOUND_ERRCODE = "P0002"
NOT_ASSIGNED_ERRCODE = "P0003"
NOT_ALLOWED_ERRCODE = "P0004"
INVALID_PARAMETER_ERRCODE = "22023"
NOT_READY_ERRCODE = "P0005"


logger = logging.getLogger(__name__)

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


class SafetyDecisionInvalidError(Exception):
    """The database refused the decision's content (SQLSTATE 22023)."""

    def __init__(self) -> None:
        super().__init__("The safety decision is not valid")


class SafetyApprovalBlockedError(Exception):
    """SCRUM-60 AC6: approval waits until every arrangement review is cleared.
    outstanding is the database function's list, each item given a message,
    in the same shape as SCRUM-58's not-ready response."""

    def __init__(self, event_request_id: str, outstanding: list[dict[str, Any]]) -> None:
        super().__init__(f"Event request {event_request_id} cannot be approved yet")
        self.event_request_id = event_request_id
        self.outstanding = [
            {**item, "message": f"Still marked for review: {item.get('reason', '')}"}
            for item in outstanding
        ]


class EventTransitionService:
    """Own coordinator transitions and SCRUM-17 review decisions.

    Every operation uses a database function that locks the request and
    re-checks the latest assignment before writing. Approved -> Planning is
    SCRUM-58; the safety check, confirmation and post-submission change
    requests remain in their owning stories.
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

    def start_planning(
        self, event_request_id: str, caller_id: str
    ) -> EventRequestResponse:
        return self._advance(
            event_request_id, caller_id, EventRequestStatus.PLANNING
        )

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

    def decide_safety(
        self, event_request_id: str, officer_id: str, payload: SafetyDecision
    ) -> EventRequestResponse:
        """Record the Safety Officer's decision (SCRUM-60 AC3, AC4a, AC4b, AC6)."""
        try:
            event_request = self.event_request_service.decide_safety_review(
                event_request_id, officer_id, payload
            )
        except EventRequestRpcError as error:
            if error.errcode == NOT_FOUND_ERRCODE:
                raise EventRequestNotFoundError(event_request_id) from error
            if error.errcode == NOT_ASSIGNED_ERRCODE:
                raise EventRequestForbiddenError(event_request_id) from error
            if error.errcode == NOT_ALLOWED_ERRCODE:
                raise TransitionNotAllowedError(
                    event_request_id,
                    f"Event request {event_request_id} is not waiting for a safety check",
                ) from error
            if error.errcode == INVALID_PARAMETER_ERRCODE:
                raise SafetyDecisionInvalidError() from error
            if error.errcode == NOT_READY_ERRCODE:
                raise SafetyApprovalBlockedError(
                    event_request_id, json.loads(error.details or "[]")
                ) from error
            raise

        # After the decision is committed, as in SCRUM-17: a refused decision
        # tells nobody anything. The organiser's "confirmed" notice is SCRUM-36.
        if payload.decision == "changes_requested":
            # The decision is saved: a failed lookup must not turn it into a 502,
            # which the officer would retry into a 409. The reason stays readable
            # on the request.
            try:
                coordinator_id = self.event_request_service.latest_coordinator_id(
                    event_request_id
                )
            except SupabaseRepositoryError:
                logger.warning(
                    "Could not find the coordinator to notify of the safety changes "
                    "requested on event request %s",
                    event_request_id,
                    exc_info=True,
                )
                coordinator_id = None
            if coordinator_id is not None:
                self.notification_client.notify_safety_changes_requested(
                    event_request_id=event_request_id,
                    coordinator_id=coordinator_id,
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
