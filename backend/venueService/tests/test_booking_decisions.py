"""SCRUM-15 rule tests with local data; no booking API or database assumed."""

import pytest
from pydantic import ValidationError

from app.block_models import VenueBlock
from app.booking_decisions import (
    BookingDecisionSubject,
    ConfirmedVenueBooking,
    DecisionDetails,
    assess_booking_decision,
)
from app.models import Venue


def subject(**changes):
    return BookingDecisionSubject.model_validate(
        {
            "venue_id": "venue-1",
            "current_status": "pending",
            "start_date": "2026-10-02",
            "end_date": "2026-10-04",
            "slots": ["AM", "PM"],
        }
        | changes
    )


def venue(**changes):
    return Venue.model_validate(
        {"id": "venue-1", "name": "Hall", "location": "Campus", "max_capacity": 50}
        | changes
    )


def block(**changes):
    return VenueBlock.model_validate(
        {
            "id": "block-1",
            "venue_id": "venue-1",
            "created_by": "staff-1",
            "start_date": "2026-10-03",
            "end_date": "2026-10-05",
            "slots": ["PM"],
            "reason_category": "maintenance",
        }
        | changes
    )


def confirmed(**changes):
    return ConfirmedVenueBooking.model_validate(
        {
            "booking_id": "other-booking",
            "venue_id": "venue-1",
            "start_date": "2026-10-03",
            "end_date": "2026-10-03",
            "slots": ["PM"],
        }
        | changes
    )


def assess(**changes):
    args = {
        "booking": subject(),
        "venue": venue(),
        "decision": DecisionDetails(decision="approved"),
        "blocks": [],
        "confirmed_bookings": [],
    }
    return assess_booking_decision(**(args | changes))


# AC1-H3 (happy): a pending request with clear checks may be approved
def test_pending_request_can_be_approved_when_both_checks_are_clear():
    result = assess()
    assert result.allowed
    assert result.target_status == "approved"
    assert result.refusal_codes == []
    assert result.availability.available
    assert result.conflicting_booking_ids == []


def details(choice: str) -> DecisionDetails:
    """A valid decision of each kind; a rejection always carries a reason."""
    if choice == "rejected":
        return DecisionDetails(decision="rejected", reason="Unsuitable")
    return DecisionDetails(decision=choice)


# AC1-N3 (negative): only a pending request can receive a decision
@pytest.mark.parametrize("state", ["approved", "rejected", "cancelled", "unknown"], ids=["AC1-N3a", "AC1-N3b", "AC1-N3c", "AC1-N3d"])
@pytest.mark.parametrize("choice", ["approved", "rejected"], ids=["case1", "case2"])
def test_only_pending_requests_can_receive_a_decision(state, choice):
    result = assess(
        booking=subject(current_status=state), decision=details(choice)
    )
    assert not result.allowed
    assert result.target_status is None
    assert result.refusal_codes == ["request_not_pending"]


# AC2-P2 (partition): a rejection keeps its reason and optional alternative without lookups
@pytest.mark.parametrize(
    "reason,alternative",
    [("Unsuitable arrangement", None), ("Unavailable", "Try venue 2")],
    ids=["AC2-P2a", "AC2-P2b"],
)
def test_rejection_preserves_optional_details_without_availability_lookups(
    reason, alternative
):
    result = assess(
        decision=DecisionDetails(
            decision="rejected", reason=reason, suggested_alternative=alternative
        ),
        blocks=None,
        confirmed_bookings=None,
    )
    assert result.allowed
    assert result.target_status == "rejected"
    assert result.reason == reason
    assert result.suggested_alternative == alternative
    assert result.availability is None


# AC2-P3 (partition): a request can be rejected even when its slot is blocked and booked
def test_rejection_is_still_possible_when_slot_is_blocked_and_booked():
    result = assess(
        decision=DecisionDetails(decision="rejected", reason="Slot unavailable"),
        blocks=[block()],
        confirmed_bookings=[confirmed()],
    )
    assert result.allowed
    assert result.target_status == "rejected"


# AC5-H2 (happy): a block added since the request prevents approval with recordable evidence
def test_block_added_since_request_prevents_approval_and_returns_recordable_evidence():
    assert assess().allowed
    result = assess(blocks=[block()])
    assert not result.allowed
    assert result.target_status is None
    assert result.refusal_codes == ["active_block"]
    conflict = result.availability.conflicts[0]
    assert conflict.block_id == "block-1"
    assert conflict.start_date.isoformat() == "2026-10-03"
    assert conflict.end_date.isoformat() == "2026-10-04"
    # SCRUM-65: the shared part in time, 12:00-18:00 (the PM slot).
    assert (conflict.start_minute, conflict.end_minute) == (720, 1080)


# AC5-P4a (partition): an unavailable venue prevents approval
def test_unavailable_venue_or_unsupported_slot_prevents_approval():
    result = assess(venue=venue(status="blocked"))
    assert not result.allowed
    assert result.refusal_codes == ["venue_unavailable"]


# AC5-P4b (partition): the venue's old operating slots no longer refuse approval (SCRUM-65)
def test_operating_slots_no_longer_refuse_approval():
    assert assess(venue=venue(operating_slots=["AM"])).allowed


# AC5-P5 (partition): lifted or unrelated blocks do not prevent approval
@pytest.mark.parametrize(
    "changes",
    [{"status": "lifted"}, {"venue_id": "other-venue"}, {"slots": ["NIGHT"]}],
    ids=["AC5-P5a", "AC5-P5b", "AC5-P5c"],
)
def test_lifted_or_unrelated_blocks_do_not_prevent_approval(changes):
    assert assess(blocks=[block(**changes)]).allowed


# AC6-H2 (happy): a booking confirmed since the request prevents approval
def test_booking_confirmed_since_request_prevents_approval():
    assert assess().allowed
    result = assess(confirmed_bookings=[confirmed()])
    assert not result.allowed
    assert result.target_status is None
    assert result.refusal_codes == ["booking_conflict"]
    assert result.conflicting_booking_ids == ["other-booking"]


# AC6-B2 (boundary): confirmed booking dates are inclusive
@pytest.mark.parametrize(
    "day,allowed",
    [
        ("2026-10-01", True),
        ("2026-10-02", False),
        ("2026-10-04", False),
        ("2026-10-05", True),
    ],
    ids=["AC6-B2a", "AC6-B2b", "AC6-B2c", "AC6-B2d"],
)
def test_confirmed_booking_date_boundaries_are_inclusive(day, allowed):
    result = assess(confirmed_bookings=[confirmed(start_date=day, end_date=day)])
    assert result.allowed is allowed


# AC6-P3 (partition): bookings at other venues or slots do not conflict
@pytest.mark.parametrize("changes", [{"venue_id": "other"}, {"slots": ["NIGHT"]}], ids=["AC6-P3a", "AC6-P3b"])
def test_confirmed_bookings_at_other_venues_or_slots_do_not_conflict(changes):
    assert assess(confirmed_bookings=[confirmed(**changes)]).allowed


# AC6-P4 (partition): every conflicting booking is returned once in a stable order
def test_all_conflicts_are_returned_with_unique_stable_booking_ids():
    result = assess(
        venue=venue(status="blocked", operating_slots=["AM"]),
        blocks=[block()],
        confirmed_bookings=[
            confirmed(booking_id="b"),
            confirmed(booking_id="a"),
            confirmed(),
        ],
    )
    assert result.refusal_codes == [
        "venue_unavailable",
        "active_block",
        "booking_conflict",
    ]
    assert result.conflicting_booking_ids == ["a", "b", "other-booking"]
    duplicate = assess(confirmed_bookings=[confirmed(), confirmed()])
    assert duplicate.conflicting_booking_ids == ["other-booking"]


# AC5-N1 (negative): a failed block or booking lookup never permits approval
@pytest.mark.parametrize(
    "changes,codes",
    [
        ({"blocks": None}, ["block_check_unavailable"]),
        ({"confirmed_bookings": None}, ["booking_check_unavailable"]),
        (
            {"blocks": None, "confirmed_bookings": None},
            ["block_check_unavailable", "booking_check_unavailable"],
        ),
    ],
    ids=["AC5-N1a", "AC5-N1b", "AC5-N1c"],
)
def test_missing_checks_never_become_permission_to_approve(changes, codes):
    result = assess(**changes)
    assert not result.allowed
    assert result.target_status is None
    assert result.refusal_codes == codes


# AC1-N4 (negative): another venue's data cannot approve a request
def test_wrong_venue_cannot_supply_approval_evidence():
    result = assess(venue=venue(id="other-venue"))
    assert not result.allowed
    assert result.refusal_codes == ["venue_mismatch"]


# AC1-X2 (cross-cutting): assessing a decision changes none of its inputs
@pytest.mark.parametrize("choice", ["approved", "rejected"], ids=["AC1-X2a", "AC1-X2b"])
def test_assessment_does_not_mutate_request_venue_or_availability_data(choice):
    inputs = {
        "booking": subject(),
        "venue": venue(),
        "decision": details(choice),
        "blocks": [block()],
        "confirmed_bookings": [confirmed()],
    }
    before = [
        item.model_dump()
        for item in [
            inputs["booking"],
            inputs["venue"],
            inputs["decision"],
            *inputs["blocks"],
            *inputs["confirmed_bookings"],
        ]
    ]
    assess_booking_decision(**inputs)
    after = [
        item.model_dump()
        for item in [
            inputs["booking"],
            inputs["venue"],
            inputs["decision"],
            *inputs["blocks"],
            *inputs["confirmed_bookings"],
        ]
    ]
    assert after == before


# AC1-N5 (negative): an invalid requested period cannot be assessed
@pytest.mark.parametrize(
    "changes",
    [{"slots": []}, {"start_minute": 600, "end_minute": 600}, {"end_date": "2026-10-01"}],
    ids=["AC1-N5a", "AC1-N5b", "AC1-N5c"],
)
def test_invalid_requested_period_cannot_be_assessed(changes):
    with pytest.raises(ValidationError):
        subject(**changes)


# AC2-N3 (negative): invalid decisions, including a rejection without a reason, are refused
@pytest.mark.parametrize(
    "details",
    [
        {"decision": "pending"},
        {"decision": "approved", "reason": "Rejected"},
        {"decision": "approved", "suggested_alternative": "Another venue"},
        {"decision": "rejected"},
        {"decision": "rejected", "reason": "   "},
    ],
    ids=["AC2-N3a", "AC2-N3b", "AC2-N3c", "AC2-N3d", "AC2-N3e"],
)
def test_invalid_decision_details_are_rejected(details):
    with pytest.raises(ValidationError):
        DecisionDetails(**details)


# AC2-P4 (partition): a blank alternative is treated as absent and the reason is trimmed
def test_blank_optional_alternative_is_absent():
    decision = DecisionDetails(
        decision="rejected", reason=" Unsuitable ", suggested_alternative=" "
    )
    assert decision.reason == "Unsuitable"
    assert decision.suggested_alternative is None
