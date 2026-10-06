from typing import Any, NoReturn

from app.models.event_request import (
    EventChangeDecision,
    EventChangeRequestCreate,
    EventChangeRequestResponse,
    EventClarificationResponse,
    EventRequestCreate,
    EventRequestResponse,
    EventRequestStatus,
    EventRequestSubmission,
    EventRequestUpdate,
    EventReviewDecisionResponse,
)
from app.repositories import EventRequestRepository
from app.repositories.event_request_repository import EventRequestRpcError


class EventRequestNotFoundError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} was not found")
        self.event_request_id = event_request_id


class EventRequestForbiddenError(Exception):
    """The caller may view the request (same client organisation) but not change it."""

    def __init__(self, event_request_id: str) -> None:
        super().__init__("Insufficient permissions")
        self.event_request_id = event_request_id


class EventRequestNotDraftError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} is no longer a Draft")
        self.event_request_id = event_request_id


class ClarificationResponseNotAllowedError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(
            f"Event request {event_request_id} is not accepting a clarification response"
        )
        self.event_request_id = event_request_id


class EventChangeRequestConflictError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} cannot accept that change action")
        self.event_request_id = event_request_id


class EventChangeRequestForbiddenError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__("Only the currently assigned coordinator can decide this change request")
        self.event_request_id = event_request_id


class EventRequestTransitionConflictError(Exception):
    """The row wasn't in from_status when the transition was attempted —
    a concurrent change, since callers check status before transitioning."""

    def __init__(self, event_request_id: str, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Event request {event_request_id} was not {from_status!r} when "
            f"transitioning to {to_status!r}"
        )
        self.event_request_id = event_request_id


class EventRequestService:
    """Owns Draft and submission rules independently of Supabase transport."""

    def __init__(self, repository: EventRequestRepository) -> None:
        self.repository = repository

    def create(
        self, payload: EventRequestCreate, organiser_id: str
    ) -> EventRequestResponse:
        values = payload.model_dump(mode="json")
        values.update(
            {
                "organiser_id": organiser_id,
                "status": EventRequestStatus.DRAFT.value,
            }
        )
        return self._row_to_response(self.repository.create(values))

    def create_submission(
        self, payload: EventRequestSubmission, organiser_id: str
    ) -> EventRequestResponse:
        values = payload.model_dump(mode="json")
        values.update(
            {
                "organiser_id": organiser_id,
                "status": EventRequestStatus.SUBMITTED.value,
            }
        )
        return self._row_to_response(self.repository.create(values))

    def list_for_organiser(self, organiser_id: str) -> list[EventRequestResponse]:
        """The organiser's own requests plus their organisation's non-Draft ones."""
        rows = {row["id"]: row for row in self.repository.list_for_organiser(organiser_id)}
        organisation_id = self.repository.get_organisation_id(organiser_id)
        if organisation_id is not None:
            for row in self.repository.list_shared_with_organisation(organisation_id):
                rows.setdefault(row["id"], row)
        return sorted(
            (self._row_to_response(row) for row in rows.values()),
            key=lambda request: request.created_at,
            reverse=True,
        )

    def get_viewable(
        self, event_request_id: str, organiser_id: str
    ) -> EventRequestResponse:
        """Read access for an organiser: the owner, or a same-organisation
        colleague once the request has left Draft (SCRUM-39)."""
        row = self.repository.get_by_id(event_request_id)
        if row is None or not self._can_view(row, organiser_id):
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def _can_view(self, row: dict[str, Any], organiser_id: str) -> bool:
        if row["organiser_id"] == organiser_id:
            return True
        organisation_id = row.get("organisation_id")
        return (
            row["status"] != EventRequestStatus.DRAFT.value
            and organisation_id is not None
            and organisation_id == self.repository.get_organisation_id(organiser_id)
        )

    def _refusal(self, event_request_id: str, organiser_id: str) -> Exception:
        """403 for a colleague who can already see the request, else 404."""
        row = self.repository.get_by_id(event_request_id)
        if row is not None and self._can_view(row, organiser_id):
            return EventRequestForbiddenError(event_request_id)
        return EventRequestNotFoundError(event_request_id)

    def list_by_status(self, status: EventRequestStatus) -> list[EventRequestResponse]:
        """Unscoped lookup across every organiser, for a caller whose remit is
        the whole queue rather than one organiser's own requests.
        """
        rows = self.repository.list_by_status(status.value)
        return [self._row_to_response(row) for row in rows]

    def list_by_statuses(
        self, statuses: set[EventRequestStatus]
    ) -> list[EventRequestResponse]:
        return sorted(
            (request for status in statuses for request in self.list_by_status(status)),
            key=lambda request: request.created_at,
            reverse=True,
        )

    def get(self, event_request_id: str, organiser_id: str) -> EventRequestResponse:
        row = self.repository.get_for_organiser(event_request_id, organiser_id)
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def get_by_id(self, event_request_id: str) -> EventRequestResponse:
        """Unscoped lookup for a caller who isn't the owning organiser."""
        row = self.repository.get_by_id(event_request_id)
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def get_by_ids(
        self, event_request_ids: list[str]
    ) -> list[EventRequestResponse]:
        rows = self.repository.get_by_ids(event_request_ids)
        return [self._row_to_response(row) for row in rows]

    def transition_status(
        self,
        event_request_id: str,
        from_status: EventRequestStatus,
        to_status: EventRequestStatus,
    ) -> EventRequestResponse:
        row = self.repository.update_status(
            event_request_id, from_status.value, to_status.value
        )
        if row is None:
            raise EventRequestTransitionConflictError(
                event_request_id, from_status.value, to_status.value
            )
        return self._row_to_response(row)

    def advance_by_coordinator(
        self,
        event_request_id: str,
        coordinator_id: str,
        to_status: EventRequestStatus,
    ) -> EventRequestResponse:
        """Coordinator transitions run through one database function, which
        re-checks the assignment under a row lock; the RPC errcodes stay in
        the repo layer and are mapped by the caller."""
        row = self.repository.advance_by_coordinator(
            event_request_id, coordinator_id, to_status.value
        )
        return self._row_to_response(row)

    def decide_by_coordinator(
        self,
        event_request_id: str,
        coordinator_id: str,
        decision: EventRequestStatus,
        reason: str | None,
    ) -> EventRequestResponse:
        row = self.repository.decide_by_coordinator(
            event_request_id,
            coordinator_id,
            decision.value,
            reason,
        )
        return self._row_to_response(row)

    def resume_review_by_coordinator(
        self, event_request_id: str, coordinator_id: str
    ) -> EventRequestResponse:
        row = self.repository.resume_review_by_coordinator(
            event_request_id, coordinator_id
        )
        return self._row_to_response(row)

    def list_review_decisions(
        self, event_request_id: str
    ) -> list[EventReviewDecisionResponse]:
        rows = self.repository.list_review_decisions(event_request_id)
        return [EventReviewDecisionResponse.model_validate(row) for row in rows]

    def create_change_request(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventChangeRequestCreate,
    ) -> EventChangeRequestResponse:
        try:
            row = self.repository.create_change_request(
                event_request_id,
                organiser_id,
                payload.explanation,
                payload.proposed_changes(),
            )
        except EventRequestRpcError as error:
            self._raise_change_request_error(error, event_request_id)
        return EventChangeRequestResponse.model_validate(row)

    def list_change_requests(
        self, event_request_id: str
    ) -> list[EventChangeRequestResponse]:
        return [
            EventChangeRequestResponse.model_validate(row)
            for row in self.repository.list_change_requests(event_request_id)
        ]

    def decide_change_request(
        self,
        event_request_id: str,
        change_request_id: str,
        coordinator_id: str,
        payload: EventChangeDecision,
    ) -> EventChangeRequestResponse:
        """Retained internal primitive; the public API refuses decisions until
        arrangement review and change notification workflows are integrated.
        """
        try:
            row = self.repository.decide_change_request(
                event_request_id,
                change_request_id,
                coordinator_id,
                payload.decision.value,
                payload.reason,
            )
        except EventRequestRpcError as error:
            self._raise_change_request_error(error, event_request_id)
        return EventChangeRequestResponse.model_validate(row)

    @staticmethod
    def _raise_change_request_error(
        error: EventRequestRpcError, event_request_id: str
    ) -> NoReturn:
        if error.errcode == "P0002":
            raise EventRequestNotFoundError(event_request_id) from error
        if error.errcode == "P0003":
            raise EventChangeRequestForbiddenError(event_request_id) from error
        if error.errcode == "P0004":
            raise EventChangeRequestConflictError(event_request_id) from error
        raise error

    def update(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventRequestUpdate,
    ) -> EventRequestResponse:
        changes = payload.model_dump(exclude_unset=True, mode="json")
        if not changes:
            return self.get(event_request_id, organiser_id)

        row = self.repository.update_for_organiser(
            event_request_id,
            organiser_id,
            changes,
        )
        if row is None:
            self._raise_not_found_or_not_draft(event_request_id, organiser_id)
        return self._row_to_response(row)

    def submit(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventRequestSubmission,
    ) -> EventRequestResponse:
        row = self.repository.submit_for_organiser(
            event_request_id,
            organiser_id,
            payload.model_dump(mode="json"),
        )
        if row is None:
            self._raise_not_found_or_not_draft(event_request_id, organiser_id)
        return self._row_to_response(row)

    def respond_to_clarification(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventClarificationResponse,
    ) -> EventReviewDecisionResponse:
        try:
            row = self.repository.respond_to_clarification(
                event_request_id, organiser_id, payload.response
            )
        except EventRequestRpcError as error:
            if error.errcode == "P0002":
                raise self._refusal(event_request_id, organiser_id) from error
            if error.errcode == "P0004":
                raise ClarificationResponseNotAllowedError(event_request_id) from error
            raise
        return EventReviewDecisionResponse.model_validate(row)

    def delete(self, event_request_id: str, organiser_id: str) -> None:
        deleted = self.repository.delete_for_organiser(event_request_id, organiser_id)
        if not deleted:
            self._raise_not_found_or_not_draft(event_request_id, organiser_id)

    def _raise_not_found_or_not_draft(
        self, event_request_id: str, organiser_id: str
    ) -> NoReturn:
        row = self.repository.get_for_organiser(event_request_id, organiser_id)
        if row is None:
            raise self._refusal(event_request_id, organiser_id)
        raise EventRequestNotDraftError(event_request_id)

    @staticmethod
    def _row_to_response(row: dict[str, Any]) -> EventRequestResponse:
        return EventRequestResponse.model_validate(row)
