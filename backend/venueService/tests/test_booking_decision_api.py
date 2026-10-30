"""SCRUM-15: Venue Staff approve or reject booking requests through the API.

Case IDs match docs/testcases/scrum_15_testcases.md. Requests are seeded into
the in-memory store directly, because submission (SCRUM-32) needs
eventRequestService.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from time_support import slot_times

from app import booking_decision_store
from app.booking_models import BookingRequest
from app.booking_repository import booking_repository
from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app

client = TestClient(app)
STAFF = "00000000-0000-0000-0000-000000000001"  # the conftest caller


@pytest.fixture(autouse=True)
def _clear_refusals():
    booking_decision_store.memory_decision_store.clear()
    yield
    booking_decision_store.memory_decision_store.clear()


def make_venue(**overrides) -> str:
    body = {"name": "Hall", "location": "Campus", "max_capacity": 50} | overrides
    response = client.post("/venues", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def make_request(venue_id: str, start: str, end: str, slots: list[str]) -> str:
    booking = BookingRequest(
        venue_id=venue_id,
        requested_by=str(uuid4()),
        event_request_id=str(uuid4()),
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        slots=slots,
    )
    return booking_repository.create(booking).id


def make_block(venue_id: str, start: str, end: str, slots: list[str]) -> str:
    response = client.post(
        f"/venues/{venue_id}/blocks",
        json={
            "start_date": start,
            "end_date": end,
            **slot_times(slots),
            "reason_category": "maintenance",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def decide(booking_id: str, **body):
    return client.post(f"/booking-requests/{booking_id}/decision", json=body)


def status_of(booking_id: str) -> str:
    return booking_repository.get(booking_id).status.value


def refusals(booking_id: str) -> list[dict]:
    response = client.get(f"/booking-requests/{booking_id}/refusals")
    assert response.status_code == 200
    return response.json()


def signed_in_as(role: str) -> None:
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000009", roles=(role,)
    )
    app.dependency_overrides.pop(require_venue_staff, None)


# AC1-H1 (happy): approving a free slot books it and records the decider and time
def test_approving_a_free_slot_books_it():
    request = make_request(make_venue(), "2026-10-20", "2026-10-21", ["AM"])

    response = decide(request, decision="approved")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["decided_by"] == STAFF
    assert body["decided_at"] is not None
    assert body["decision_reason"] is None and body["suggested_alternative"] is None
    assert status_of(request) == "approved"
    assert refusals(request) == []


# AC1-H2 (happy): rejecting records the trimmed reason and alternative
def test_rejecting_records_reason_and_alternative():
    request = make_request(make_venue(), "2026-10-20", "2026-10-20", ["AM"])

    response = decide(
        request,
        decision="rejected",
        reason=" Hall under repair ",
        suggested_alternative=" Try Orchard Studio ",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["decision_reason"] == "Hall under repair"
    assert body["suggested_alternative"] == "Try Orchard Studio"
    assert body["decided_by"] == STAFF


# AC2-P1 (partition): the suggested alternative is optional
def test_rejecting_without_an_alternative():
    request = make_request(make_venue(), "2026-10-20", "2026-10-20", ["AM"])

    response = decide(request, decision="rejected", reason="Unsuitable")

    assert response.status_code == 200
    assert response.json()["suggested_alternative"] is None


# AC1-N1 (negative): a decided request cannot be decided again and stays unchanged
@pytest.mark.parametrize(
    "first,second",
    [
        ({"decision": "approved"}, {"decision": "rejected", "reason": "Late"}),
        ({"decision": "rejected", "reason": "No"}, {"decision": "approved"}),
    ],
    ids=["AC1-N1a", "AC1-N1b"],
)
def test_a_decided_request_cannot_be_decided_again(first, second):
    request = make_request(make_venue(), "2026-10-20", "2026-10-20", ["AM"])
    assert decide(request, **first).status_code == 200
    before = booking_repository.get(request).model_dump()

    response = decide(request, **second)

    assert response.status_code == 409
    assert response.json()["detail"] == "Booking request has already been decided"
    assert booking_repository.get(request).model_dump() == before


# AC1-N2 (negative): an unknown request returns 404
@pytest.mark.parametrize("booking_id", ["missing", str(uuid4())], ids=["AC1-N2a", "AC1-N2b"])
def test_unknown_request_is_not_found(booking_id):
    assert decide(booking_id, decision="approved").status_code == 404


# AC1-X1 (cross-cutting): only Venue Staff can decide; others change nothing
@pytest.mark.parametrize(
    "role",
    ["event_coordinator", "event_organiser", "attendee"],
    ids=["AC1-X1a", "AC1-X1b", "AC1-X1c"],
)
def test_only_venue_staff_can_decide(role):
    request = make_request(make_venue(), "2026-10-20", "2026-10-20", ["AM"])
    signed_in_as(role)

    response = decide(request, decision="approved")

    assert response.status_code == 403
    assert status_of(request) == "pending"
    assert booking_decision_store.memory_decision_store.list_refusals(request) == []


# AC2-N1, AC2-N2 (negative): a rejection without a reason or an approval with details is refused unchanged
@pytest.mark.parametrize(
    "body",
    [
        {"decision": "rejected"},
        {"decision": "rejected", "reason": "   "},
        {"decision": "approved", "reason": "ok"},
        {"decision": "approved", "suggested_alternative": "Hall B"},
        {"decision": "pending"},
        {"decision": "approved", "decided_by": STAFF},
    ],
    ids=["AC2-N1a", "AC2-N1b", "AC2-N2a", "AC2-N2b", "AC2-N2c", "AC2-N2d"],
)
def test_invalid_decisions_change_nothing(body):
    request = make_request(make_venue(), "2026-10-20", "2026-10-20", ["AM"])

    assert decide(request, **body).status_code == 422
    assert status_of(request) == "pending"


# AC5-H1 (happy): an overlapping active block refuses approval and the refusal is recorded
def test_an_active_block_refuses_approval_and_is_recorded():
    venue = make_venue()
    block = make_block(venue, "2026-10-21", "2026-10-21", ["AM"])
    request = make_request(venue, "2026-10-20", "2026-10-21", ["AM"])

    response = decide(request, decision="approved")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "Approval refused",
        "refusal_codes": ["active_block"],
        "conflicting_block_ids": [block],
        "conflicting_booking_ids": [],
        "conflicting_hold_ids": [],
    }
    assert status_of(request) == "pending"
    [refusal] = refusals(request)
    assert refusal["booking_request_id"] == request
    assert refusal["refused_by"] == STAFF
    assert refusal["refusal_codes"] == ["active_block"]
    assert refusal["conflicting_block_ids"] == [block]
    assert refusal["created_at"]


# AC5-P1 (partition): a catalogue-blocked venue refuses approval
def test_unavailable_venue_or_slot_refuses_approval():
    venue = make_venue()
    assert client.patch(f"/venues/{venue}", json={"status": "blocked"}).status_code == 200
    request = make_request(venue, "2026-10-20", "2026-10-20", ["AM"])

    response = decide(request, decision="approved")

    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["venue_unavailable"]
    assert status_of(request) == "pending"
    assert [r["refusal_codes"] for r in refusals(request)] == [["venue_unavailable"]]


# AC5-P2 (partition): an old non-operating slot no longer refuses; every venue runs 07:00-24:00 (SCRUM-65)
def test_operating_slots_no_longer_refuse_approval():
    venue = make_venue()
    assert client.patch(f"/venues/{venue}", json={"operating_slots": ["AM", "PM"]}).status_code == 200
    request = make_request(venue, "2026-10-20", "2026-10-20", ["NIGHT"])

    assert decide(request, decision="approved").status_code == 200
    assert refusals(request) == []


# AC5-P3 (partition): lifted blocks and blocks on other slots or dates do not refuse
def test_lifted_and_non_overlapping_blocks_do_not_refuse():
    from app.block_models import BlockStatus
    from app.block_repository import block_repository

    venue = make_venue()
    lifted = make_block(venue, "2026-10-20", "2026-10-20", ["AM"])
    block_repository.get(lifted).status = BlockStatus.LIFTED
    make_block(venue, "2026-10-20", "2026-10-20", ["PM"])
    make_block(venue, "2026-10-21", "2026-10-21", ["AM"])
    request = make_request(venue, "2026-10-20", "2026-10-20", ["AM"])

    assert decide(request, decision="approved").status_code == 200
    assert refusals(request) == []


# AC5-B1 (boundary): block dates are inclusive
@pytest.mark.parametrize(
    "block_start,block_end,expected",
    [("2026-10-19", "2026-10-20", 409), ("2026-10-22", "2026-10-23", 200)],
    ids=["AC5-B1a", "AC5-B1b"],
)
def test_block_boundaries_are_inclusive(block_start, block_end, expected):
    venue = make_venue()
    make_block(venue, block_start, block_end, ["AM"])
    request = make_request(venue, "2026-10-20", "2026-10-21", ["AM"])

    assert decide(request, decision="approved").status_code == expected


# AC5-X1 (cross-cutting): only Venue Staff can read the refusal log
@pytest.mark.parametrize(
    "role,expected",
    [("venue_staff", 200), ("event_coordinator", 403), ("event_organiser", 403)],
    ids=["AC5-X1a", "AC5-X1b", "AC5-X1c"],
)
def test_only_venue_staff_can_read_refusals(role, expected):
    venue = make_venue()
    make_block(venue, "2026-10-20", "2026-10-20", ["AM"])
    request = make_request(venue, "2026-10-20", "2026-10-20", ["AM"])
    assert decide(request, decision="approved").status_code == 409
    signed_in_as(role)

    response = client.get(f"/booking-requests/{request}/refusals")

    assert response.status_code == expected


# AC6-H1 (happy): an approved overlapping booking refuses approval as a conflict
def test_an_approved_overlap_is_refused_as_a_conflict():
    venue = make_venue()
    first = make_request(venue, "2026-10-20", "2026-10-21", ["AM"])
    second = make_request(venue, "2026-10-21", "2026-10-21", ["AM"])
    assert decide(first, decision="approved").status_code == 200

    response = decide(second, decision="approved")

    assert response.status_code == 409
    assert response.json()["detail"]["refusal_codes"] == ["booking_conflict"]
    assert response.json()["detail"]["conflicting_booking_ids"] == [first]
    assert status_of(second) == "pending"
    assert status_of(first) == "approved"
    assert [r["conflicting_booking_ids"] for r in refusals(second)] == [[first]]


# AC6-P1 (partition): pending and rejected requests never conflict
def test_pending_and_rejected_requests_do_not_conflict():
    venue = make_venue()
    make_request(venue, "2026-10-20", "2026-10-20", ["AM"])
    rejected = make_request(venue, "2026-10-20", "2026-10-20", ["AM"])
    assert decide(rejected, decision="rejected", reason="No").status_code == 200
    request = make_request(venue, "2026-10-20", "2026-10-20", ["AM"])

    assert decide(request, decision="approved").status_code == 200


# AC6-P2 (partition): other venues and non-overlapping slots do not conflict
def test_other_venues_and_slots_do_not_conflict():
    venue, other = make_venue(), make_venue()
    assert decide(make_request(other, "2026-10-20", "2026-10-20", ["AM"]), decision="approved").status_code == 200
    assert decide(make_request(venue, "2026-10-20", "2026-10-20", ["PM"]), decision="approved").status_code == 200

    request = make_request(venue, "2026-10-20", "2026-10-20", ["AM"])

    assert decide(request, decision="approved").status_code == 200


# AC6-B1 (boundary): booking date boundaries are inclusive
def test_booking_boundaries_are_inclusive():
    venue = make_venue()
    assert decide(make_request(venue, "2026-10-20", "2026-10-21", ["AM"]), decision="approved").status_code == 200

    sharing_last_day = make_request(venue, "2026-10-21", "2026-10-22", ["AM"])
    day_after = make_request(venue, "2026-10-22", "2026-10-23", ["AM"])

    assert decide(sharing_last_day, decision="approved").status_code == 409
    assert decide(day_after, decision="approved").status_code == 200


# AC6-X1 (cross-cutting): two simultaneous approvals of overlapping requests cannot both succeed
def test_simultaneous_overlapping_approvals_cannot_both_succeed(monkeypatch):
    venue = make_venue()
    first = make_request(venue, "2026-10-20", "2026-10-21", ["AM"])
    second = make_request(venue, "2026-10-21", "2026-10-22", ["AM"])
    original = booking_decision_store.assess_booking_decision

    def slow_assessment(**kwargs):
        # Widen the race window: without the venue lock both would approve.
        time.sleep(0.2)
        return original(**kwargs)

    monkeypatch.setattr(booking_decision_store, "assess_booking_decision", slow_assessment)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(
            pool.map(lambda b: TestClient(app).post(f"/booking-requests/{b}/decision", json={"decision": "approved"}).status_code, [first, second])
        )

    assert codes == [200, 409]
    assert sorted([status_of(first), status_of(second)]) == ["approved", "pending"]
