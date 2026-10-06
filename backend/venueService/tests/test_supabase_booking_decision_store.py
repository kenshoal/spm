"""SupabaseBookingDecisionStore against a fake Data API (no network).

Case IDs match docs/testcases/scrum_15_testcases.md (SB-1).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.booking_decision_store import (
    BookingAlreadyDecidedError,
    BookingNotFoundError,
    SupabaseBookingDecisionStore,
)
from app.booking_decisions import DecisionDetails
from app.supabase_repository import SupabaseRepositoryError

URL = "https://project.supabase.co"
KEY = "sb_secret_test"
BOOKING = "2a192261-5e90-4398-90ff-1a2d0eaaff01"
STAFF = "00000000-0000-0000-0000-000000000001"


def row(**overrides) -> dict:
    return {
        "id": BOOKING,
        "venue_id": "2a192261-5e90-4398-90ff-1a2d0eaaff00",
        "requested_by": "00000000-0000-0000-0000-000000000002",
        "event_request_id": "00000000-0000-0000-0000-000000000003",
        "start_date": "2026-10-20",
        "end_date": "2026-10-20",
        "slots": ["AM"],
        "status": "pending",
        "created_at": "2026-10-07T01:00:00+00:00",
    } | overrides


def store(status: int, body: object, calls: list | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return httpx.Response(status, json=body)

    return SupabaseBookingDecisionStore(URL, KEY, transport=httpx.MockTransport(handle))


# SB-1 (cross-cutting): an approval calls the locked function with the verified decider
def test_approval_calls_the_database_function():
    calls: list[httpx.Request] = []
    approved = row(status="approved", decided_by=STAFF, decided_at="2026-10-07T02:00:00+00:00")

    outcome = store(200, {"outcome": "approved", "booking": approved}, calls).decide(
        BOOKING, DecisionDetails(decision="approved"), STAFF
    )

    assert calls[0].url.path == "/rest/v1/rpc/decide_venue_booking_request"
    assert json.loads(calls[0].content) == {
        "p_booking_request_id": BOOKING,
        "p_decision": "approved",
        "p_decided_by": STAFF,
        "p_decision_reason": None,
        "p_suggested_alternative": None,
    }
    assert calls[0].headers["apikey"] == KEY
    assert not outcome.refused
    assert outcome.booking.status.value == "approved"


# SB-1 (cross-cutting): a refused approval returns its reason codes and conflicting ids
def test_refused_approval_returns_the_reasons():
    body = {
        "outcome": "refused",
        "refusal_codes": ["active_block", "booking_conflict"],
        "conflicting_block_ids": ["b1"],
        "conflicting_booking_ids": ["r1"],
        "booking": row(),
    }

    outcome = store(200, body).decide(BOOKING, DecisionDetails(decision="approved"), STAFF)

    assert outcome.refused
    assert outcome.refusal_codes == ["active_block", "booking_conflict"]
    assert outcome.conflicting_block_ids == ["b1"]
    assert outcome.conflicting_booking_ids == ["r1"]
    assert outcome.booking.status.value == "pending"


# SB-1 (cross-cutting): database error codes map to not found, already decided or a sanitised failure
@pytest.mark.parametrize(
    "code,error",
    [
        ("P0002", BookingNotFoundError),
        ("55000", BookingAlreadyDecidedError),
        ("42501", SupabaseRepositoryError),
    ],
    ids=["SB-1a", "SB-1b", "SB-1c"],
)
def test_database_errors_are_mapped(code, error):
    failing = store(400, {"code": code, "message": "PRIVATE DATABASE DETAIL"})

    with pytest.raises(error) as caught:
        failing.decide(BOOKING, DecisionDetails(decision="rejected", reason="No"), STAFF)

    assert "PRIVATE" not in str(caught.value)


# SB-1 (cross-cutting): a malformed id never reaches the database
def test_malformed_id_is_not_found_without_a_request():
    calls: list[httpx.Request] = []

    with pytest.raises(BookingNotFoundError):
        store(200, {}, calls).decide("not-a-uuid", DecisionDetails(decision="approved"), STAFF)

    assert calls == []


# SB-1 (cross-cutting): the refusal log is read oldest first for one request
def test_refusals_are_listed_for_one_request():
    calls: list[httpx.Request] = []
    refusal = {
        "id": "00000000-0000-0000-0000-0000000000aa",
        "booking_request_id": BOOKING,
        "refused_by": STAFF,
        "refusal_codes": ["venue_unavailable"],
        "conflicting_block_ids": [],
        "conflicting_booking_ids": [],
        "created_at": "2026-10-07T03:00:00+00:00",
    }

    [listed] = store(200, [refusal], calls).list_refusals(BOOKING)

    assert calls[0].url.path == "/rest/v1/venue_booking_refusals"
    assert calls[0].url.params["booking_request_id"] == f"eq.{BOOKING}"
    assert calls[0].url.params["order"] == "created_at.asc,id.asc"
    assert listed.refusal_codes == ["venue_unavailable"]
