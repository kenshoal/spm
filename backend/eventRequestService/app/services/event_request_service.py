from typing import Any, NoReturn

from app.models.event_request import (
    EventRequestCreate,
    EventRequestResponse,
    EventRequestStatus,
    EventRequestSubmission,
    EventRequestUpdate,
)
from app.repositories import EventRequestRepository


class EventRequestNotFoundError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} was not found")
        self.event_request_id = event_request_id


class EventRequestNotDraftError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} is no longer a Draft")
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
        rows = self.repository.list_for_organiser(organiser_id)
        return [self._row_to_response(row) for row in rows]

    def list_by_status(self, status: EventRequestStatus) -> list[EventRequestResponse]:
        """Unscoped lookup across every organiser, for a caller whose remit is
        the whole queue rather than one organiser's own requests.
        """
        rows = self.repository.list_by_status(status.value)
        return [self._row_to_response(row) for row in rows]

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

    def delete(self, event_request_id: str, organiser_id: str) -> None:
        deleted = self.repository.delete_for_organiser(event_request_id, organiser_id)
        if not deleted:
            self._raise_not_found_or_not_draft(event_request_id, organiser_id)

    def _raise_not_found_or_not_draft(
        self, event_request_id: str, organiser_id: str
    ) -> NoReturn:
        row = self.repository.get_for_organiser(event_request_id, organiser_id)
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        raise EventRequestNotDraftError(event_request_id)

    @staticmethod
    def _row_to_response(row: dict[str, Any]) -> EventRequestResponse:
        return EventRequestResponse.model_validate(row)
