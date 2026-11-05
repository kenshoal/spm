"""EventRequestClient against a fake eventRequestService (SCRUM-33).

Every test carries its case ID from docs/testcases/scrum_33_testcases.md.
"""

import httpx
import pytest
from fastapi import HTTPException
from requirements_support import C1, C2, E1, GALA_DATES, FakeEventService

from app.config import get_settings
from app.event_requests_client import get_event_request_client


# AC6-X5 (cross-cutting): both reads carry the caller's own token, assignment first, and the snapshot is returned
def test_snapshot_reads_assignment_then_event_with_callers_token() -> None:
    events = FakeEventService()

    snapshot = events.client().snapshot_for_coordinator(E1, "abc", C1)

    assert events.paths() == [
        f"/event-requests/{E1}/coordinator",
        f"/event-requests/{E1}",
    ]
    assert all(r.headers["authorization"] == "Bearer abc" for r in events.requests)
    assert all("apikey" not in r.headers for r in events.requests)
    assert snapshot.status == "Planning"
    assert snapshot.event_name == "Annual Gala"
    assert snapshot.proposed_date_times == GALA_DATES


# AC6-X6 (cross-cutting): an assignment to a different Coordinator is not found and the event is never read
def test_assignment_to_another_coordinator_is_not_found() -> None:
    events = FakeEventService()
    events.coordinator_id = C2

    with pytest.raises(HTTPException) as error:
        events.client().snapshot_for_coordinator(E1, "abc", C1)

    assert error.value.status_code == 404
    assert error.value.detail == "Event request not found"
    assert events.paths() == [f"/event-requests/{E1}/coordinator"]


# AC6-X7 (cross-cutting): the read-path check makes only the assignment call
def test_assert_assigned_reads_only_the_assignment() -> None:
    events = FakeEventService()

    result = events.client().assert_assigned(E1, "abc", C1)

    assert result is None
    assert events.paths() == [f"/event-requests/{E1}/coordinator"]
    assert events.requests[0].headers["authorization"] == "Bearer abc"


# AC6-N1 (negative): a 403 or 404 from eventRequestService, on either read, is reported as not found
@pytest.mark.parametrize(
    ("reply_on", "code"),
    [("coordinator", 403), ("coordinator", 404), ("event", 404)],
    ids=["AC6-N1 assignment 403", "AC6-N1 assignment 404", "AC6-N1 event 404"],
)
def test_refusal_from_event_service_is_not_found(reply_on: str, code: int) -> None:
    events = FakeEventService()
    reply = httpx.Response(code, json={"detail": "nope"})
    if reply_on == "coordinator":
        events.coordinator_reply = reply
    else:
        events.event_reply = reply

    with pytest.raises(HTTPException) as error:
        events.client().snapshot_for_coordinator(E1, "abc", C1)

    assert error.value.status_code == 404
    assert error.value.detail == "Event request not found"


# AC6-N2 (negative): a 401 from eventRequestService is passed on as an invalid session, on both paths
@pytest.mark.parametrize("method", ["assert_assigned", "snapshot_for_coordinator"])
def test_unauthorised_reply_is_invalid_session(method: str) -> None:
    events = FakeEventService()
    events.coordinator_reply = httpx.Response(401, json={"detail": "Invalid session"})

    with pytest.raises(HTTPException) as error:
        getattr(events.client(), method)(E1, "abc", C1)

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid session"


# AC6-N3 (negative): an unreachable, slow or failing eventRequestService is a 502
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        httpx.Response(500, json={"detail": "boom"}),
    ],
    ids=["AC6-N3 connect error", "AC6-N3 timeout", "AC6-N3 500 reply"],
)
def test_unavailable_event_service_is_bad_gateway(failure: object) -> None:
    events = FakeEventService()
    if isinstance(failure, httpx.Response):
        events.coordinator_reply = failure
    else:
        events.error = failure  # type: ignore[assignment]

    with pytest.raises(HTTPException) as error:
        events.client().snapshot_for_coordinator(E1, "abc", C1)

    assert error.value.status_code == 502
    assert error.value.detail == "Event request service unavailable"


# AC6-N4 (negative): a malformed reply from eventRequestService is a 502, never a pass
@pytest.mark.parametrize(
    ("reply_on", "reply"),
    [
        ("coordinator", httpx.Response(200, text="not json")),
        ("coordinator", httpx.Response(200, json=[{"coordinator_id": C1}])),
        ("coordinator", httpx.Response(200, json={"event_request_id": E1})),
        ("coordinator", httpx.Response(200, json={"coordinator_id": 1})),
        ("event", httpx.Response(200, json={"event_name": "Annual Gala"})),
    ],
    ids=[
        "AC6-N4 non-JSON",
        "AC6-N4 list body",
        "AC6-N4 no coordinator_id",
        "AC6-N4 coordinator_id not a string",
        "AC6-N4 event without status",
    ],
)
def test_malformed_reply_is_bad_gateway(reply_on: str, reply: httpx.Response) -> None:
    events = FakeEventService()
    if reply_on == "coordinator":
        events.coordinator_reply = reply
    else:
        events.event_reply = reply

    with pytest.raises(HTTPException) as error:
        events.client().snapshot_for_coordinator(E1, "abc", C1)

    assert error.value.status_code == 502
    assert error.value.detail == "Event request service unavailable"


# AC6-N5 (negative): an invalid EVENT_REQUEST_SERVICE_URL is a 503, and nothing is called
def test_invalid_service_url_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("EVENT_REQUEST_SERVICE_URL", "not a url")
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as error:
            get_event_request_client()
    finally:
        get_settings.cache_clear()

    assert error.value.status_code == 503
    assert error.value.detail == "Service is not configured"
