"""EventRequestClient against a fake eventRequestService (SCRUM-32).

Every test carries its case ID from docs/testcases/scrum_32_testcases.md.
"""

import httpx
import pytest
from fastapi import HTTPException

from app.event_requests import EventRequestClient

EVENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CALLER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def client_for(handler) -> tuple[EventRequestClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return (
        EventRequestClient("http://events.test", transport=httpx.MockTransport(record)),
        seen,
    )


def ok_handler(coordinator_id: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/coordinator"):
            return httpx.Response(200, json={"coordinator_id": coordinator_id})
        return httpx.Response(
            200,
            json={
                "event_name": "Annual Gala",
                "expected_attendance": 120,
                "venue_requirements": "Stage",
                "organiser_id": "someone-else",
            },
        )

    return handler


# AC6-X7 (cross-cutting): the caller's own token is sent on both reads, assignment first
def test_both_reads_use_the_callers_token() -> None:
    client, seen = client_for(ok_handler(CALLER))

    snapshot = client.snapshot_for_coordinator(EVENT_ID, "abc", CALLER)

    assert [request.url.path for request in seen] == [
        f"/event-requests/{EVENT_ID}/coordinator",
        f"/event-requests/{EVENT_ID}",
    ]
    assert all(request.headers["authorization"] == "Bearer abc" for request in seen)
    assert snapshot.event_name == "Annual Gala"
    assert snapshot.expected_attendance == 120
    assert snapshot.venue_requirements == "Stage"


# AC6-X7 (cross-cutting): an assignment to a different Coordinator is reported as not found
def test_assignment_to_someone_else_is_not_found() -> None:
    client, seen = client_for(ok_handler(OTHER))

    with pytest.raises(HTTPException) as error:
        client.snapshot_for_coordinator(EVENT_ID, "abc", CALLER)

    assert error.value.status_code == 404
    assert error.value.detail == "Event request not found"
    # The event itself is never read for a Coordinator who is not assigned.
    assert [request.url.path for request in seen] == [
        f"/event-requests/{EVENT_ID}/coordinator"
    ]


# AC6-N1 (negative): a 403 or 404 from the event service is reported as not found
@pytest.mark.parametrize("code", [403, 404])
def test_refusal_from_the_event_service_is_not_found(code: int) -> None:
    client, _ = client_for(lambda request: httpx.Response(code, json={"detail": "x"}))

    with pytest.raises(HTTPException) as error:
        client.snapshot_for_coordinator(EVENT_ID, "abc", CALLER)

    assert (error.value.status_code, error.value.detail) == (404, "Event request not found")


# AC6-N3 (negative): a reply with no coordinator id, or not an object, is a bad gateway
@pytest.mark.parametrize("body", [{}, {"coordinator_id": 7}, ["x"]])
def test_malformed_assignment_is_a_bad_gateway(body: object) -> None:
    client, _ = client_for(lambda request: httpx.Response(200, json=body))

    with pytest.raises(HTTPException) as error:
        client.snapshot_for_coordinator(EVENT_ID, "abc", CALLER)

    assert error.value.status_code == 502


# AC3-N1 (negative): only the assignment is read, and another coordinator is "not found"
def test_require_coordinator_reads_only_the_assignment() -> None:
    client, seen = client_for(ok_handler(CALLER))

    client.require_coordinator(EVENT_ID, "abc", CALLER)

    assert [request.url.path for request in seen] == [
        f"/event-requests/{EVENT_ID}/coordinator"
    ]
    assert seen[0].headers["authorization"] == "Bearer abc"

    other, _ = client_for(ok_handler(OTHER))
    with pytest.raises(HTTPException) as error:
        other.require_coordinator(EVENT_ID, "abc", CALLER)
    assert (error.value.status_code, error.value.detail) == (404, "Event request not found")
