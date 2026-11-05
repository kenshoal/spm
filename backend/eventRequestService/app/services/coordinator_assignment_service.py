from typing import Any

from app.models.coordinator_assignment import (
    CoordinatorAssignmentResponse,
    CoordinatorAssignRequest,
    CurrentAssignmentResponse,
)
from app.models.event_request import EventRequestResponse, EventRequestStatus
from app.repositories.coordinator_assignment_repository import (
    CoordinatorAssignmentRepository,
    CoordinatorAssignmentRpcError,
)
from app.services.event_request_service import (
    EventRequestNotFoundError,
    EventRequestService,
)
from app.services.notification_client import NotificationClient

_TERMINAL_STATUSES = {
    EventRequestStatus.COMPLETED,
    EventRequestStatus.CANCELLED,
    EventRequestStatus.REJECTED,
    EventRequestStatus.WITHDRAWN,
}

# Statuses in which a request has (or awaits) a responsible Coordinator and
# can still be reassigned — everything after submission and before closure.
_IN_FLIGHT_STATUSES = (
    EventRequestStatus.SUBMITTED,
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.CHANGES_REQUESTED,
    EventRequestStatus.APPROVED,
    EventRequestStatus.PLANNING,
    EventRequestStatus.SAFETY_REVIEW,
    EventRequestStatus.CONFIRMED,
    EventRequestStatus.POSTPONED,
)


_STALE_VIEW = (
    "The Coordinator for this request changed after you opened it. Refresh and try again"
)


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
        notification_client: NotificationClient | None = None,
    ) -> None:
        self.repository = repository
        self.event_request_service = event_request_service
        self.notification_client = notification_client or NotificationClient(None)

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

        # Early refusal for a stale view; the database repeats it under the row lock.
        latest = self.repository.latest_for_event_request(event_request_id)
        if (latest["coordinator_id"] if latest else None) != payload.expected_coordinator_id:
            raise CoordinatorAssignmentNotAllowedError(event_request_id, _STALE_VIEW)

        try:
            row = self.repository.create(
                {
                    "event_request_id": event_request_id,
                    "coordinator_id": payload.coordinator_id,
                    "expected_coordinator_id": payload.expected_coordinator_id,
                    "assigned_by": assigned_by,
                }
            )
        except CoordinatorAssignmentRpcError as error:
            if error.errcode == "P0002":
                raise EventRequestNotFoundError(event_request_id) from error
            if error.errcode == "P0006":
                raise CoordinatorAssignmentNotAllowedError(
                    event_request_id, _STALE_VIEW
                ) from error
            if error.errcode == "P0004":
                raise CoordinatorAssignmentNotAllowedError(
                    event_request_id,
                    "The event request no longer accepts coordinator assignment",
                ) from error
            if error.errcode == "P0005":
                raise CoordinatorAssignmentNotAllowedError(
                    event_request_id,
                    "The selected user is not an Event Coordinator",
                ) from error
            raise
        self.notification_client.notify_coordinator_assigned(
            event_request_id=event_request_id,
            coordinator_id=payload.coordinator_id,
            assigned_by=assigned_by,
        )
        previous = self._previous_coordinator_id(event_request_id, int(row["id"]))
        if previous is not None and previous != payload.coordinator_id:
            self.notification_client.notify_coordinator_unassigned(
                event_request_id=event_request_id,
                coordinator_id=previous,
                assigned_by=assigned_by,
            )
        return CoordinatorAssignmentResponse.model_validate(row)

    def _previous_coordinator_id(
        self, event_request_id: str, new_assignment_id: int
    ) -> str | None:
        """The coordinator held the request just before this assignment.

        The assignment RPC inserts under the event row lock, ids only grow and
        rows are never deleted, so the highest id below the new one is exactly
        the previous holder, even when reassignments race (SCRUM-62 AC4)."""
        earlier = [
            row
            for row in self.repository.list_for_event_requests([event_request_id])
            if int(row["id"]) < new_assignment_id
        ]
        if not earlier:
            return None
        return str(max(earlier, key=lambda row: int(row["id"]))["coordinator_id"])

    def list_awaiting_assignment(self) -> list[EventRequestResponse]:
        """Submitted requests nobody is responsible for yet. Assignments are
        append-only and there is no unassign operation, so "has any assignment
        row" is exactly "has a current Coordinator".
        """
        submitted = self.event_request_service.list_by_status(
            EventRequestStatus.SUBMITTED
        )
        if not submitted:
            return []
        assigned = self.repository.assigned_event_request_ids(
            [request.id for request in submitted]
        )
        return [request for request in submitted if request.id not in assigned]

    def list_current_assignments(self) -> list[CurrentAssignmentResponse]:
        """In-flight requests that have a Coordinator, with the current one —
        what the Event Coordinator Lead needs to find a request to reassign."""
        in_flight = [
            request
            for status in _IN_FLIGHT_STATUSES
            for request in self.event_request_service.list_by_status(status)
        ]
        if not in_flight:
            return []

        latest: dict[str, dict[str, Any]] = {}
        for row in self.repository.list_for_event_requests(
            [request.id for request in in_flight]
        ):
            request_id = row["event_request_id"]
            if request_id not in latest or int(row["id"]) > int(
                latest[request_id]["id"]
            ):
                latest[request_id] = row

        current = [
            CurrentAssignmentResponse(
                event_request=request,
                assignment=CoordinatorAssignmentResponse.model_validate(
                    latest[request.id]
                ),
            )
            for request in in_flight
            if request.id in latest
        ]
        return sorted(
            current, key=lambda item: item.event_request.created_at, reverse=True
        )

    def get_current(self, event_request_id: str) -> CoordinatorAssignmentResponse:
        self.event_request_service.get_by_id(event_request_id)
        row = self.repository.latest_for_event_request(event_request_id)
        if row is None:
            raise CoordinatorAssignmentNotFoundError(event_request_id)
        return CoordinatorAssignmentResponse.model_validate(row)

    def list_requests_for_coordinator(
        self, coordinator_id: str
    ) -> list[EventRequestResponse]:
        """The requests whose latest assignment is this coordinator — a
        reassigned-away coordinator must not keep seeing the request, so
        "ever assigned" isn't enough; the highest-id assignment decides."""
        mine = self.repository.list_for_coordinator(coordinator_id)
        if not mine:
            return []

        candidates = {row["event_request_id"] for row in mine}
        latest: dict[str, dict[str, Any]] = {}
        for row in self.repository.list_for_event_requests(sorted(candidates)):
            request_id = row["event_request_id"]
            if request_id not in latest or int(row["id"]) > int(
                latest[request_id]["id"]
            ):
                latest[request_id] = row

        assigned_ids = sorted(
            request_id
            for request_id, row in latest.items()
            if row["coordinator_id"] == coordinator_id
        )
        return self.event_request_service.get_by_ids(assigned_ids)
