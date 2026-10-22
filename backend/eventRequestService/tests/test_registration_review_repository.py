"""SCRUM-35 registration persistence wire; shared paging algorithm has separate cap tests."""

import json

import httpx
from test_event_registration_reviews import ACK_TIME, COORDINATOR, EVENT, review

from app.repositories.event_request_repository import SupabaseEventRequestRepository


# AC3-X18, AC3-X19 (cross-cutting): all-history reads remain event-scoped and exact acknowledgement reaches only the audited RPC with the verified actor.
def test_registration_read_and_acknowledgement_transport_contract():
    newer = review(2, cleared_at=ACK_TIME, cleared_by=COORDINATOR)
    older = review(1)
    acknowledged = {**older, "cleared_at": ACK_TIME, "cleared_by": COORDINATOR}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[newer, older] if len(seen) == 1 else [])
        return httpx.Response(200, json=acknowledged)

    repository = SupabaseEventRequestRepository("https://project.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler))
    assert repository.list_registration_reviews(EVENT) == [newer, older]
    assert len(seen) == 2  # Actual-empty continuation, rather than treating a short page as exhaustion.
    for request in seen:
        assert request.method == "GET"
        assert request.url.path == "/rest/v1/event_registration_reviews"
        assert request.url.params["event_request_id"] == f"eq.{EVENT}"
        assert request.url.params["order"] == "raised_at.desc,id.desc"
        assert "cleared_at" not in request.url.params
        assert request.headers["apikey"] == "sb_secret_test"
    assert "or" not in seen[0].url.params
    cursor = seen[1].url.params["or"]
    assert f"raised_at.lt.{older['raised_at']}" in cursor
    assert f"raised_at.eq.{older['raised_at']}" in cursor
    assert f"id.lt.{older['id']}" in cursor

    assert repository.acknowledge_registration_review(EVENT, older["id"], COORDINATOR) == acknowledged
    assert len(seen) == 3
    request = seen[-1]
    assert request.method == "POST"
    assert request.url.path == "/rest/v1/rpc/acknowledge_event_registration_review"
    assert request.headers["Accept"] == "application/vnd.pgrst.object+json"
    assert json.loads(request.content) == {"p_event_request_id": EVENT, "p_review_id": older["id"], "p_coordinator_id": COORDINATOR}
