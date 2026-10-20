"""SCRUM-64 shared outstanding-read contract through the real HTTP adapter."""

import json
from copy import deepcopy

import httpx
from test_arrangement_reviews import COORDINATOR, EVENT, fixture, normalized
from test_organisation_access import client_for

from app.repositories import SupabaseEventRequestRepository


# AC5-X3 (cross-cutting): coordinator persistence reads use the shared event-scoped outstanding helper without changing the public contract.
def test_real_repository_reads_outstanding_reviews_through_shared_helper():
    seeded, assignments = fixture()
    before = deepcopy(seeded.arrangement_review_rows)
    captured = []
    # The approved helper returns outstanding ordered rows; its real SQL owns filtering/order.
    expected = [deepcopy(seeded.arrangement_review_rows[i]) for i in (4, 3, 0)]

    def transport(request):
        captured.append(
            (request.method, request.url.path, dict(request.url.params),
             json.loads(request.content) if request.content else None)
        )
        if request.url.path == "/rest/v1/event_requests":
            return httpx.Response(200, json=[seeded.rows[EVENT]])
        if request.method == "POST" and request.url.path == "/rest/v1/rpc/get_outstanding_arrangement_reviews":
            page_number = sum(call[0] == "POST" for call in captured)
            return httpx.Response(200, json=deepcopy(expected) if page_number == 1 else [])
        return httpx.Response(404, json={"code": "PGRST202", "message": "Unsupported persistence path"})

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(transport),
    )
    with client_for(
        repository, COORDINATOR, ("event_coordinator",), assignments
    ) as client:
        response = client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    assert response.status_code == 200, response.text
    assert captured[0][:2] == ("GET", "/rest/v1/event_requests")
    assert captured[0][2]["id"] == f"eq.{EVENT}"
    assert len(captured) == 3  # Event authorisation read, facts page, terminal empty page.
    for method, path, params, body in captured[1:]:
        assert (method, path) == ("POST", "/rest/v1/rpc/get_outstanding_arrangement_reviews")
        assert body == {"p_event_request_id": EVENT}
        assert params["order"] == "raised_at.desc,id.desc"
        assert params["limit"] == "1000"
    assert "or" not in captured[1][2]
    last = expected[-1]
    assert captured[2][2]["or"] == (
        f"(raised_at.lt.{last['raised_at']},"
        f"and(raised_at.eq.{last['raised_at']},id.lt.{last['id']}))"
    )
    assert normalized(response.json()) == normalized(expected)
    assert seeded.arrangement_review_rows == before
