"""SCRUM64 actual adapter wiring; transport is HTTPMockTransport, not Supabase."""

import json
from copy import deepcopy

import httpx
import pytest
from test_arrangement_review_actions import (
    CLEARED_TIME,
    VENUE_STAFF,
    action_fixture,
    evidence,
)
from test_organisation_access import client_for

from app.repositories import SupabaseEventRequestRepository


@pytest.mark.parametrize("operation", ["queue", "clear"], ids=["AC5-X6", "AC4-X2"])
# AC5-X6, AC4-X2 (cross-cutting): real domain query and exact clear RPC must preserve scope, verified identity and database error codes.
def test_real_domain_queue_and_clear_transport_contract(operation):
    seeded, assignments = action_fixture()
    original = deepcopy(seeded.arrangement_review_rows[4])
    cleared = {**original, "cleared_at": CLEARED_TIME, "cleared_by": VENUE_STAFF}
    # Prepared first page already satisfies the server-side domain/outstanding/order contract.
    queue_page = [
        deepcopy(next(row for row in seeded.arrangement_review_rows if row["id"].endswith(f"{number:012d}")))
        for number in (1, 9, 3)
    ]
    calls = []
    conflict = False

    def transport(request):
        calls.append(request)
        assert request.headers["apikey"] == "sb_secret_test"
        if operation == "queue":
            assert request.method == "GET"
            assert request.url.path == "/rest/v1/arrangement_reviews"
            expected_query = {
                "arrangement": "eq.venue_booking",
                "cleared_at": "is.null",
                "order": "raised_at.desc,id.desc",
                "limit": "1000",
                "select": "*",
            }
            if len(calls) == 2:
                last = queue_page[-1]
                expected_query["or"] = (
                    f"(raised_at.lt.{last['raised_at']},"
                    f"and(raised_at.eq.{last['raised_at']},id.lt.{last['id']}))"
                )
            assert dict(request.url.params) == expected_query
            assert len(calls) <= 2, "An empty continuation page must terminate the read"
            return httpx.Response(200, json=queue_page if len(calls) == 1 else [])
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/clear_arrangement_review"
        assert dict(request.url.params) == {}
        assert json.loads(request.content) == {
            "p_review_id": original["id"],
            "p_actor_id": VENUE_STAFF,
            "p_allowed_arrangements": ["venue_booking"],
        }
        # The existing adapter convention requests one composite row as JSON.
        assert request.headers["accept"] == "application/vnd.pgrst.object+json"
        if conflict:
            return httpx.Response(
                400,
                json={"code": "P0004", "message": "internal_storage_detail conflict"},
            )
        return httpx.Response(200, json=cleared)

    repository = SupabaseEventRequestRepository(
        "https://project.supabase.co",
        "sb_secret_test",
        transport=httpx.MockTransport(transport),
    )
    with client_for(repository, VENUE_STAFF, ("venue_staff",), assignments) as client:
        if operation == "queue":
            response = client.get(
                "/arrangement-reviews", params={"arrangement": "venue_booking"}
            )
            assert response.status_code == 200
            assert [row["id"] for row in response.json()] == [
                f"00000000-0000-4000-8000-{number:012d}" for number in (1, 9, 3)
            ]
            assert len(calls) == 2
        else:
            response = client.post(f"/arrangement-reviews/{original['id']}/clear")
            assert response.status_code == 200
            assert evidence(response.json()) == evidence(cleared)
            conflict = True
            refused = client.post(f"/arrangement-reviews/{original['id']}/clear")
            assert refused.status_code == 409
            assert (
                refused.json()["detail"]["code"] == "ARRANGEMENT_REVIEW_ALREADY_CLEARED"
            )
            assert "internal_storage_detail" not in refused.text
            assert len(calls) == 2
