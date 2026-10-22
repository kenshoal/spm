"""Distinct actual HTTP adapter seams; transport double models only server queries/caps."""

from copy import deepcopy

import httpx
import pytest

from app.repositories import SupabaseEventRequestRepository, SupabaseRepositoryError

EVENT = "35000000-0000-4000-8000-000000000020"
OTHER = "35000000-0000-4000-8000-000000000099"
CHANGE = "35000000-0000-4000-8000-000000000030"


def rows():
    return [
        {"id": f"35000000-0000-4000-8000-{number:012d}", "event_request_id": EVENT, "status": status,
         "venue_id": "35000000-0000-4000-8000-000000000100", "start_date": "2026-11-20", "end_date": "2026-11-21", "start_minute": 600, "end_minute": 720}
        for number, status in enumerate(["pending", "approved", "cancelled", "rejected", "pending", "approved", "pending"], 1)
    ]


def page(request, records):
    query = request.url.params
    selected = records
    if query.get("event_request_id"):
        selected = [row for row in selected if row["event_request_id"] == query["event_request_id"].removeprefix("eq.")]
    if query.get("id"):
        selected = [row for row in selected if row["id"] > query["id"].removeprefix("gt.")]
    return deepcopy(sorted(selected, key=lambda row: row["id"])[:min(3, int(query.get("limit", "3")))])


# AC3-X8 (cross-cutting): exact proposal scope and complete raw booking pages must survive a server cap without filtering domain statuses or guessing empty success.
def test_scoped_proposal_and_complete_booking_keyset_transport():
    expected = rows()
    source = [*deepcopy(expected), {**expected[0], "id": "35000000-0000-4000-8000-000000000098", "event_request_id": OTHER}]
    protected = deepcopy(source)
    proposal = {"id": CHANGE, "event_request_id": EVENT, "status": "Pending", "proposed_changes": {"proposed_date_times": ["2026-11-22T02:00:00Z"]}}
    captured = []

    def handler(request):
        captured.append(request)
        if request.url.path == "/rest/v1/event_change_requests":
            query = request.url.params
            found = query.get("id") == f"eq.{CHANGE}" and query.get("event_request_id") == f"eq.{EVENT}"
            return httpx.Response(200, json=[proposal] if found else [])
        return httpx.Response(200, json=page(request, source))

    repository = SupabaseEventRequestRepository("https://project.test", "test-service-key", transport=httpx.MockTransport(handler))
    try:
        actual_proposal = repository.get_change_request(EVENT, CHANGE)
        actual = repository.list_event_venue_bookings(EVENT)
    finally:
        repository.close()
    assert actual_proposal == proposal
    assert actual == expected
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/rest/v1/event_change_requests"
    assert dict(captured[0].url.params) == {"select": "*", "id": f"eq.{CHANGE}", "event_request_id": f"eq.{EVENT}", "limit": "1"}
    calls = captured[1:]
    assert len(calls) == 4, "Three capped nonempty pages must be followed by an actual empty page"
    assert [request.url.params.get("id") for request in calls] == [None, f"gt.{expected[2]['id']}", f"gt.{expected[5]['id']}", f"gt.{expected[6]['id']}"]
    for request in calls:
        assert request.method == "GET"
        assert request.url.path == "/rest/v1/venue_booking_requests"
        assert request.url.params["event_request_id"] == f"eq.{EVENT}"
        assert request.url.params["select"] == "*"
        assert request.url.params["order"] == "id.asc"
        assert int(request.url.params["limit"]) > 3
        assert "status" not in request.url.params
    assert source == protected


# AC3-N14 (negative): a later failed booking page cannot turn the first capped page into a successful incomplete preview.
def test_late_booking_page_failure_raises_instead_of_returning_partial_rows():
    source = rows()
    protected = deepcopy(source)
    captured = []

    def handler(request):
        captured.append(request)
        if len(captured) > 1:
            return httpx.Response(503, json={"message": "private late-page failure"})
        return httpx.Response(200, json=page(request, source))

    repository = SupabaseEventRequestRepository("https://project.test", "test-service-key", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SupabaseRepositoryError):
            repository.list_event_venue_bookings(EVENT)
    finally:
        repository.close()
    assert len(captured) == 2
    assert captured[1].url.params["id"] == f"gt.{source[2]['id']}"
    assert source == protected
