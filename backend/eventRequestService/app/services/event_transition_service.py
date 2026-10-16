import json
from typing import Any

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
NOT_READY_ERRCODE = "P0005"


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


def _outstanding_message(item: dict[str, Any]) -> str:
    kind = item.get("kind")
    if kind == "no_venue_booking":
        return "No venue is booked for this event"
    if kind == "venue_booking_pending":
        return (
            f"The booking for {item.get('venue_name')} is still waiting for a decision"
        )
    if kind == "equipment_not_reserved":
        return (
            f"{item.get('equipment_type')}: "
            f"{item.get('reserved')} of {item.get('required')} reserved"
        )
    return "Something is still outstanding"


class SafetyReviewNotReadyError(Exception):
    """SCRUM-58 AC3a: the event still has outstanding bookings or equipment.
    outstanding is the database function's list, each item given a message."""

    def __init__(self, event_request_id: str, outstanding: list[dict[str, Any]]) -> None:
        super().__init__(
            f"Event request {event_request_id} is not ready for safety review"
        )
        self.event_request_id = event_request_id
        self.outstanding = [
            {**item, "message": _outstanding_message(item)} for item in outstanding
        ]


class DecisionReasonRequiredError(Exception):
    """A returned or rejected request must explain what the organiser needs to know."""

    def __init__(self, decision: EventRequestStatus) -> None:
        super().__init__(f"A reason is required when the decision is {decision.value}")


class EventTransitionService:
    """Own coordinator transitions and SCRUM-17 review decisions.

    Every operation uses a database function that locks the request and
    re-checks the latest assignment before writing. Approved -> Planning and
    Planning -> Safety Review are SCRUM-58; the Safety Officer's decision
    (SCRUM-60) and post-submission change requests remain in their owning
    stories.
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

    def send_for_safety_review(
        self, event_request_id: str, caller_id: str
    ) -> EventRequestResponse:
        try:
            return self.event_request_service.send_for_safety_review(
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
                    f"Cannot send event request {event_request_id} for safety "
                    "review from its current status",
                ) from error
            if error.errcode == NOT_READY_ERRCODE:
                raise SafetyReviewNotReadyError(
                    event_request_id, json.loads(error.details or "[]")
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
