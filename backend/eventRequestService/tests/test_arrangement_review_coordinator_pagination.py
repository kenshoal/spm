"""AC5 public coordinator completeness with a capped table-valued RPC transport."""

import json
import re
from copy import deepcopy
from datetime import datetime

import httpx
import pytest
from test_arrangement_reviews import COORDINATOR, EVENT, fixture, normalized, review
from test_organisation_access import client_for

from app.repositories import SupabaseEventRequestRepository


class CappedReviewRpc:
    """Prepared native-helper facts; HTTP cap/continuation only, not SQL or auth logic."""

    def __init__(self, count, *, fail_later=False, clear_earlier=False):
        seeded, self.assignments = fixture()
        self.event = deepcopy(seeded.rows[EVENT])
        # Both domains belong in one event queue. Native SQL separately proves
        # event/outstanding filtering; prepared results obey that interface.
        self.expected = [review(n, arrangement="venue_booking" if n % 2 else "equipment_reservation") for n in range(count, 0, -1)]
        self.expected[-1]["raised_at"] = "2026-10-14T00:00:00Z"
        self.rows = deepcopy(self.expected)
        self.initial = deepcopy(self.rows)
        self.calls = []
        self.previous_ids = []
        self.fail_later = fail_later
        self.clear_earlier = clear_earlier

    def __call__(self, request):
        if request.method == "GET" and request.url.path == "/rest/v1/event_requests":
            assert request.url.params["id"] == f"eq.{EVENT}"
            return httpx.Response(200, json=[self.event])
        self.calls.append(request)
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/get_outstanding_arrangement_reviews"
        assert json.loads(request.content) == {"p_event_request_id": EVENT}
        if len(self.calls) > 1 and self.fail_later:
            return httpx.Response(503, json={"message": "private helper continuation failure"})
        if len(self.calls) == 2 and self.clear_earlier:
            for row in self.rows:
                if row["id"] in self.previous_ids:
                    row["cleared_at"] = "2026-10-17T00:00:00Z"
                    row["cleared_by"] = COORDINATOR
        # Simulate the helper's prepared outstanding result after the external
        # clear; no caller permissions or production mutation rules live here.
        rows = [deepcopy(row) for row in self.rows if row["cleared_at"] is None]
        params = request.url.params
        if params.get("order"):
            assert params["order"] == "raised_at.desc,id.desc"
        if params.get("or"):
            match = re.fullmatch(r"\(raised_at\.lt\.(.+),and\(raised_at\.eq\.(.+),id\.lt\.([^,)]+)\)\)", params["or"])
            assert match and match[1] == match[2], "Unexpected PostgREST cursor"
            key = datetime.fromisoformat(match[1]), match[3]
            rows = [row for row in rows if (datetime.fromisoformat(row["raised_at"]), row["id"]) < key]
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 3))
        if "range" in request.headers:
            start, end = map(int, request.headers["range"].split("-"))
            offset, limit = start, end - start + 1
        page = rows[offset:offset + min(3, limit)]
        self.previous_ids.extend(row["id"] for row in page)
        span = f"{offset}-{offset + len(page) - 1}" if page else "*"
        return httpx.Response(200, json=page, headers={"Content-Range": f"{span}/*", "Range-Unit": "items"})


def read_coordinator_queue(server):
    repository = SupabaseEventRequestRepository("https://project.supabase.co", "sb_secret_test", transport=httpx.MockTransport(server))
    try:
        with client_for(repository, COORDINATOR, ("event_coordinator",), server.assignments) as client:
            return client.get(f"/event-requests/{EVENT}/arrangement-reviews")
    finally:
        repository.close()


@pytest.mark.parametrize("count", [2, 3, 7], ids=["AC5-B5", "AC5-B6", "AC5-B7"])
# AC5-B5, AC5-B6, AC5-B7 (boundary): coordinator reads retain every full event-scoped review below, at and beyond an unknown RPC response cap.
def test_coordinator_queue_preserves_complete_ordered_rpc_evidence(count):
    server = CappedReviewRpc(count)
    response = read_coordinator_queue(server)
    assert response.status_code == 200, response.text
    assert normalized(response.json()) == normalized(server.expected)
    assert server.rows == server.initial


# AC5-N7 (negative): failure after one RPC page cannot expose a partial outstanding list as successful evidence.
def test_coordinator_later_rpc_page_failure_is_safe_outage():
    server = CappedReviewRpc(7, fail_later=True)
    response = read_coordinator_queue(server)
    assert response.status_code == 502
    assert response.json() == {"detail": "Arrangement reviews unavailable"}
    assert len(server.calls) == 2
    assert server.rows == server.initial


# AC5-X15 (cross-cutting): clearing already-read reviews must not skip outstanding coordinator evidence during continuation.
def test_coordinator_continuation_retains_unread_rows_after_clear():
    server = CappedReviewRpc(7, clear_earlier=True)
    response = read_coordinator_queue(server)
    assert response.status_code == 200, response.text
    assert normalized(response.json()) == normalized(server.expected)
    outstanding = {row["id"] for row in server.rows if row["cleared_at"] is None}
    assert outstanding <= {row["id"] for row in response.json()}
