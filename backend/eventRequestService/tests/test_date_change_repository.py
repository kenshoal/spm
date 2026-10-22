"""SCRUM35 date transaction wire; actual native behavior is verified separately."""

import json

import httpx

from app.repositories import SupabaseEventRequestRepository


# AC3-X30 (cross-cutting): the date writer receives exactly the bound identities, reason and complete explicit plan, and returns the full saved audit without a legacy fallback.
def test_date_decision_posts_exact_five_argument_rpc_and_retains_saved_plan():
    event = "35000000-0000-4000-8000-000000000021"
    change = "35000000-0000-4000-8000-000000000031"
    plan = [{"booking_id": "35000000-0000-4000-8000-000000000001", "start_date": "2026-11-22", "end_date": "2026-11-22", "start_minute": 660, "end_minute": 750}]
    saved = {"id": change, "event_request_id": event, "status": "Approved", "coordinator_id": "coordinator-35", "decided_at": "2026-10-22T12:00:00Z", "decision_reason": "Checked full plan", "applied_booking_plan": plan}
    calls = []

    def transport(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/approve_date_event_change_request"
        assert not request.url.query
        assert request.headers["apikey"] == "sb_secret_test"
        assert request.headers["Accept"] == "application/vnd.pgrst.object+json"
        assert json.loads(request.content) == {"p_event_request_id": event, "p_change_request_id": change, "p_coordinator_id": "coordinator-35", "p_reason": "Checked full plan", "p_booking_plan": plan}
        return httpx.Response(200, json=saved)

    repository = SupabaseEventRequestRepository("https://example.test", "sb_secret_test", transport=httpx.MockTransport(transport))
    try:
        result = repository.approve_date_change_request(event, change, "coordinator-35", "Checked full plan", plan)
    finally:
        repository._client.close()
    assert result == saved
    assert len(calls) == 1
