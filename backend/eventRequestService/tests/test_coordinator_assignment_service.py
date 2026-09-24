from typing import Any

from test_coordinator_assignment_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    submit_event_request,
)

from app.models.coordinator_assignment import CoordinatorAssignRequest
from app.services.coordinator_assignment_service import CoordinatorAssignmentService
from app.services.event_request_service import EventRequestService


class SpyNotificationClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def notify_coordinator_assigned(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


# Purpose: Confirms assignment notifies the assigned Coordinator with the right details.
def test_assign_notifies_the_assigned_coordinator() -> None:
    event_requests = FakeEventRequestRepository()
    event_request_id = submit_event_request(event_requests)
    notifications = SpyNotificationClient()
    service = CoordinatorAssignmentService(
        FakeCoordinatorAssignmentRepository(),
        EventRequestService(event_requests),
        notifications,
    )

    service.assign(
        event_request_id,
        CoordinatorAssignRequest(coordinator_id="coord-1"),
        "ops-1",
    )

    assert notifications.calls == [
        {
            "event_request_id": event_request_id,
            "coordinator_id": "coord-1",
            "assigned_by": "ops-1",
        }
    ]


# Purpose: Without a notification_client, assignment still succeeds — the default is a no-op.
def test_assign_succeeds_without_a_notification_client_configured() -> None:
    event_requests = FakeEventRequestRepository()
    event_request_id = submit_event_request(event_requests)
    service = CoordinatorAssignmentService(
        FakeCoordinatorAssignmentRepository(),
        EventRequestService(event_requests),
    )

    result = service.assign(
        event_request_id,
        CoordinatorAssignRequest(coordinator_id="coord-1"),
        "ops-1",
    )

    assert result.coordinator_id == "coord-1"


# Purpose: With nothing submitted there is nothing to ask the assignments table
# about, so the queue answers without a second round trip.
def test_awaiting_assignment_skips_the_assignment_lookup_when_nothing_submitted() -> (
    None
):
    class ExplodingAssignmentRepository(FakeCoordinatorAssignmentRepository):
        def assigned_event_request_ids(self, event_request_ids: list[str]) -> set[str]:
            raise AssertionError("no submitted requests means nothing to look up")

    service = CoordinatorAssignmentService(
        ExplodingAssignmentRepository(),
        EventRequestService(FakeEventRequestRepository()),
    )

    assert service.list_awaiting_assignment() == []


# Purpose: Reassignment appends a row rather than clearing one, so a request that
# has been reassigned must still count as assigned and stay out of the queue.
def test_reassigned_request_stays_out_of_the_awaiting_queue() -> None:
    event_requests = FakeEventRequestRepository()
    event_request_id = submit_event_request(event_requests)
    assignments = FakeCoordinatorAssignmentRepository()
    service = CoordinatorAssignmentService(
        assignments, EventRequestService(event_requests)
    )
    for coordinator in ("coord-1", "coord-2"):
        service.assign(
            event_request_id,
            CoordinatorAssignRequest(coordinator_id=coordinator),
            "ops-1",
        )

    assert service.list_awaiting_assignment() == []
