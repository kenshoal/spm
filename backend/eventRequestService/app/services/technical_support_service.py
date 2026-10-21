"""Technical support requirements and assignments for one event (SCRUM-19)."""

import logging
from typing import Any

from app.models.event_request import EventRequestResponse
from app.models.technical_support import (
    AssignmentCreate,
    AssignmentResponse,
    CandidateResponse,
    EventTechnicalSupportResponse,
    RequirementCreate,
    RequirementResponse,
)
from app.repositories.coordinator_assignment_repository import (
    CoordinatorAssignmentRepository,
)
from app.repositories.technical_support_repository import (
    REQUIREMENT_NOT_FOUND_REASON,
    TechnicalSupportRepository,
    TechnicalSupportRpcError,
)
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)
from app.services.notification_client import NotificationClient
from app.services.technical_support_rules import (
    SupportNotAllowedError,
    ensure_support_allowed,
    group_by_requirement,
)

EVENT_REQUEST_NOT_FOUND = "event_request_not_found"
REQUIREMENT_NOT_FOUND = "requirement_not_found"

logger = logging.getLogger(__name__)


class TechnicalSupportNotFoundError(Exception):
    """The event or requirement is missing, or answering would disclose one.

    The code names which, so the HTTP body can be specific without revealing
    state the caller must not see (security-and-state.md §2)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class StaffNotSuitableError(Exception):
    """The chosen person does not hold the requirement's role and skill."""

    code = "staff_not_suitable"


class AlreadyAssignedError(Exception):
    """That person is already assigned to this requirement."""

    code = "already_assigned"


class TechnicalSupportService:
    """Requirements and assignments for one event's technical support.

    Reads and the caller-relationship pre-check use plain repository reads;
    both writes go through the database functions, which re-check the
    coordinator, status, requirement and suitability under the event row
    lock, so a race lost between page load and submit lands on the same
    refusals the pre-check would have given.
    """

    def __init__(
        self,
        repository: TechnicalSupportRepository,
        event_request_service: EventRequestService,
        coordinator_repository: CoordinatorAssignmentRepository,
        notification_client: NotificationClient | None = None,
    ) -> None:
        self.repository = repository
        self.event_request_service = event_request_service
        self.coordinator_repository = coordinator_repository
        self.notification_client = notification_client or NotificationClient(None)

    def record_requirement(
        self,
        event_request_id: str,
        payload: RequirementCreate,
        recorded_by: str,
    ) -> RequirementResponse:
        event = self._require_latest_coordinator(event_request_id, recorded_by)
        # Refuse before the database call: the rules module runs in the
        # service's request path, while the locked function re-checks the
        # status and stays authoritative.
        ensure_support_allowed(event.status)
        try:
            row = self.repository.record_requirement(
                {
                    "event_request_id": event_request_id,
                    "coordinator_id": recorded_by,
                    "description": payload.description,
                    "skill_tag": payload.skill_tag.value,
                }
            )
        except TechnicalSupportRpcError as error:
            raise self._map_refusal(error, event_request_id) from error
        return RequirementResponse.model_validate(row)

    def list_for_event(
        self, event_request_id: str, caller_id: str, caller_roles: tuple[str, ...]
    ) -> list[EventTechnicalSupportResponse]:
        self._require_visible(event_request_id, caller_id, caller_roles)
        grouped = group_by_requirement(
            self.repository.list_requirements(event_request_id),
            self.repository.list_assignments(event_request_id),
        )
        return [
            EventTechnicalSupportResponse(**requirement, assigned_staff=staff)
            for requirement, staff in grouped
        ]

    def list_candidates(
        self, event_request_id: str, requirement_id: str, coordinator_id: str
    ) -> list[CandidateResponse]:
        self._require_latest_coordinator(event_request_id, coordinator_id)
        requirement = self._requirement_on_event(event_request_id, requirement_id)
        return [
            CandidateResponse.model_validate(row)
            for row in self.repository.list_candidates(requirement["id"])
        ]

    def assign(
        self,
        event_request_id: str,
        requirement_id: str,
        payload: AssignmentCreate,
        assigned_by: str,
    ) -> AssignmentResponse:
        event = self._require_latest_coordinator(event_request_id, assigned_by)
        ensure_support_allowed(event.status)
        requirement = self._requirement_on_event(event_request_id, requirement_id)
        try:
            row = self.repository.assign(
                {
                    "event_request_id": event_request_id,
                    "requirement_id": requirement_id,
                    "staff_id": payload.staff_id,
                    "coordinator_id": assigned_by,
                }
            )
        except TechnicalSupportRpcError as error:
            raise self._map_refusal(error, event_request_id) from error
        assigned = AssignmentResponse.model_validate(row)
        # Best-effort, after the commit: the client logs delivery failures
        # itself, but nothing it (or any notifier) raises may undo the
        # committed assignment (D9).
        try:
            self.notification_client.notify_technical_support_assigned(
                event_request_id=event_request_id,
                event_name=event.event_name,
                requirement_id=requirement_id,
                skill_tag=str(requirement["skill_tag"]),
                staff_id=payload.staff_id,
                assigned_by=assigned_by,
                assignment_id=str(assigned.id),
            )
        except Exception:
            logger.warning(
                "Failed to notify technical support staff %s of assignment to "
                "requirement %s on event request %s",
                payload.staff_id,
                requirement_id,
                event_request_id,
                exc_info=True,
            )
        return assigned

    def _requirement_on_event(
        self, event_request_id: str, requirement_id: str
    ) -> dict[str, Any]:
        """The requirement row, only if it belongs to this event; a requirement
        of another event is reported as missing, not as someone else's."""
        requirement = self.repository.get_requirement(requirement_id)
        if requirement is None or (
            requirement["event_request_id"] != event_request_id
        ):
            raise TechnicalSupportNotFoundError(
                REQUIREMENT_NOT_FOUND,
                f"Technical support requirement {requirement_id} not found",
            )
        return requirement

    def _require_latest_coordinator(
        self, event_request_id: str, coordinator_id: str
    ) -> EventRequestResponse:
        """Only the latest-assigned coordinator acts; anyone else is told the
        request does not exist, never who holds it."""
        try:
            event = self.event_request_service.get_by_id(event_request_id)
        except EventRequestNotFoundError:
            raise self._event_not_found(event_request_id) from None
        latest = self.coordinator_repository.latest_for_event_request(
            event_request_id
        )
        if latest is None or latest["coordinator_id"] != coordinator_id:
            raise self._event_not_found(event_request_id)
        return event

    def _require_visible(
        self, event_request_id: str, caller_id: str, caller_roles: tuple[str, ...]
    ) -> None:
        if "technical_support" in caller_roles:
            # Q&A #66: Technical Support Staff see every event they may be
            # called to, but only ones that exist.
            try:
                self.event_request_service.get_by_id(event_request_id)
            except EventRequestNotFoundError:
                raise self._event_not_found(event_request_id) from None
            return
        self._require_latest_coordinator(event_request_id, caller_id)

    @staticmethod
    def _event_not_found(event_request_id: str) -> TechnicalSupportNotFoundError:
        return TechnicalSupportNotFoundError(
            EVENT_REQUEST_NOT_FOUND,
            f"Event request {event_request_id} not found",
        )

    @staticmethod
    def _map_refusal(
        error: TechnicalSupportRpcError, event_request_id: str
    ) -> Exception:
        """Map the locked database functions' refusals onto the API errors.

        P0002 names what was missing through the function's reason — the event
        check runs first, so a later P0002 is the requirement's."""
        if error.errcode == "P0002":
            if error.reason == REQUIREMENT_NOT_FOUND_REASON:
                return TechnicalSupportNotFoundError(
                    REQUIREMENT_NOT_FOUND,
                    f"Technical support requirement not found on event request "
                    f"{event_request_id}",
                )
            return TechnicalSupportNotFoundError(
                EVENT_REQUEST_NOT_FOUND,
                f"Event request {event_request_id} not found",
            )
        if error.errcode == "P0003":
            return TechnicalSupportNotFoundError(
                EVENT_REQUEST_NOT_FOUND,
                f"Event request {event_request_id} not found",
            )
        if error.errcode == "P0004":
            return SupportNotAllowedError(
                "Technical support can only be arranged for approved, planning "
                "or confirmed events"
            )
        if error.errcode == "P0005":
            return StaffNotSuitableError("This person doesn't hold the required skill")
        if error.errcode == "23505":
            return AlreadyAssignedError("Already assigned to this requirement")
        # Any other errcode is an unexpected database refusal and stays a 502
        # through the shared SupabaseRepositoryError handler.
        return error
