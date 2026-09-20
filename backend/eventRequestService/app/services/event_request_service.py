from typing import Any

from app.models.event_request import (
    EventRequestCreate,
    EventRequestResponse,
    EventRequestStatus,
    EventRequestUpdate,
)
from app.repositories import EventRequestRepository


class EventRequestNotFoundError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} was not found")
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
    """Owns draft rules independently of the Supabase transport."""

    def __init__(self, repository: EventRequestRepository) -> None:
        self.repository = repository

    def create(
        self, payload: EventRequestCreate, organiser_id: str
    ) -> EventRequestResponse:
        values = payload.model_dump(mode="json")
        values.update(
            {
                "organiser_id": None,
                "temporary_organiser_id": organiser_id,
                "status": EventRequestStatus.DRAFT.value,
            }
        )
        return self._row_to_response(self.repository.create(values))

    def list_for_organiser(self, organiser_id: str) -> list[EventRequestResponse]:
        rows = self.repository.list_for_temporary_organiser(organiser_id)
        return [self._row_to_response(row) for row in rows]

    def get(self, event_request_id: str, organiser_id: str) -> EventRequestResponse:
        row = self.repository.get_for_temporary_organiser(
            event_request_id, organiser_id
        )
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def get_by_id(self, event_request_id: str) -> EventRequestResponse:
        """Unscoped lookup for a caller who isn't the owning organiser."""
        row = self.repository.get_by_id(event_request_id)
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

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

    def update(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventRequestUpdate,
    ) -> EventRequestResponse:
        changes = payload.model_dump(exclude_unset=True, mode="json")
        if not changes:
            return self.get(event_request_id, organiser_id)

        row = self.repository.update_for_temporary_organiser(
            event_request_id,
            organiser_id,
            changes,
        )
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def delete(self, event_request_id: str, organiser_id: str) -> None:
        deleted = self.repository.delete_for_temporary_organiser(
            event_request_id, organiser_id
        )
        if not deleted:
            raise EventRequestNotFoundError(event_request_id)

    @staticmethod
    def _row_to_response(row: dict[str, Any]) -> EventRequestResponse:
        response_values = dict(row)
        response_values["organiser_id"] = (
            response_values.get("organiser_id")
            or response_values["temporary_organiser_id"]
        )
        return EventRequestResponse.model_validate(response_values)
