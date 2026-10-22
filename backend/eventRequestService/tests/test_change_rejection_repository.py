"""Distinct rejection-only PostgREST wire boundary; no business-rule fake."""
import json

import httpx
from test_event_change_rejection import REASON
from test_supabase_repository import change_response_row

from app.repositories import SupabaseEventRequestRepository


# AC4-H1 (happy): a rejected outcome uses the narrow four-argument RPC, never the dormant approval-capable primitive.
def test_rejection_posts_narrow_rpc_arguments_and_preserves_complete_response():
    expected = change_response_row(
        status="Rejected", coordinator_id="coord-1", decision_reason=REASON,
        decided_at="2026-10-19T03:00:00+00:00",
    )
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json=expected)

    repository = SupabaseEventRequestRepository(
        "https://project.test", "test-service-key", transport=httpx.MockTransport(handler),
    )
    try:
        actual = repository.decide_change_request("event-1", "change-1", "coord-1", "Rejected", REASON)
    finally:
        repository.close()
    assert actual == expected
    assert calls == [("POST", "/rest/v1/rpc/reject_event_change_request", {
        "p_event_request_id": "event-1", "p_change_request_id": "change-1",
        "p_coordinator_id": "coord-1", "p_reason": REASON,
    })]
