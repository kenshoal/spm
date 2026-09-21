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
