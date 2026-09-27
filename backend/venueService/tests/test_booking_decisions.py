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


def test_pending_request_can_be_approved_when_both_checks_are_clear():
    result = assess()
    assert result.allowed
    assert result.target_status == "approved"
    assert result.refusal_codes == []
    assert result.availability.available
    assert result.conflicting_booking_ids == []


@pytest.mark.parametrize("state", ["approved", "rejected", "cancelled", "unknown"])
@pytest.mark.parametrize("choice", ["approved", "rejected"])
def test_only_pending_requests_can_receive_a_decision(state, choice):
    result = assess(
        booking=subject(current_status=state), decision=DecisionDetails(decision=choice)
    )
    assert not result.allowed
    assert result.target_status is None
    assert result.refusal_codes == ["request_not_pending"]


@pytest.mark.parametrize(
    "reason,alternative",
    [(None, None), ("Unsuitable arrangement", None), ("Unavailable", "Try venue 2")],
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


def test_rejection_is_still_possible_when_slot_is_blocked_and_booked():
    result = assess(
        decision=DecisionDetails(decision="rejected", reason="Slot unavailable"),
        blocks=[block()],
        confirmed_bookings=[confirmed()],
    )
    assert result.allowed
    assert result.target_status == "rejected"


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
    assert conflict.slots == ["PM"]


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"status": "blocked"}, "venue_unavailable"),
        ({"operating_slots": ["AM"]}, "outside_operating_slots"),
    ],
)
def test_unavailable_venue_or_unsupported_slot_prevents_approval(changes, expected):
    result = assess(venue=venue(**changes))
    assert not result.allowed
    assert result.refusal_codes == [expected]


@pytest.mark.parametrize(
    "changes",
    [{"status": "lifted"}, {"venue_id": "other-venue"}, {"slots": ["NIGHT"]}],
)
def test_lifted_or_unrelated_blocks_do_not_prevent_approval(changes):
    assert assess(blocks=[block(**changes)]).allowed


def test_booking_confirmed_since_request_prevents_approval():
    assert assess().allowed
    result = assess(confirmed_bookings=[confirmed()])
    assert not result.allowed
    assert result.target_status is None
    assert result.refusal_codes == ["booking_conflict"]
    assert result.conflicting_booking_ids == ["other-booking"]


@pytest.mark.parametrize(
    "day,allowed",
    [
        ("2026-10-01", True),
        ("2026-10-02", False),
        ("2026-10-04", False),
        ("2026-10-05", True),
    ],
)
def test_confirmed_booking_date_boundaries_are_inclusive(day, allowed):
    result = assess(confirmed_bookings=[confirmed(start_date=day, end_date=day)])
    assert result.allowed is allowed


@pytest.mark.parametrize("changes", [{"venue_id": "other"}, {"slots": ["NIGHT"]}])
def test_confirmed_bookings_at_other_venues_or_slots_do_not_conflict(changes):
    assert assess(confirmed_bookings=[confirmed(**changes)]).allowed


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
        "outside_operating_slots",
        "active_block",
        "booking_conflict",
    ]
    assert result.conflicting_booking_ids == ["a", "b", "other-booking"]
    duplicate = assess(confirmed_bookings=[confirmed(), confirmed()])
    assert duplicate.conflicting_booking_ids == ["other-booking"]


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
)
def test_missing_checks_never_become_permission_to_approve(changes, codes):
    result = assess(**changes)
    assert not result.allowed
    assert result.target_status is None
    assert result.refusal_codes == codes


def test_wrong_venue_cannot_supply_approval_evidence():
    result = assess(venue=venue(id="other-venue"))
    assert not result.allowed
    assert result.refusal_codes == ["venue_mismatch"]


@pytest.mark.parametrize("choice", ["approved", "rejected"])
def test_assessment_does_not_mutate_request_venue_or_availability_data(choice):
    inputs = {
        "booking": subject(),
        "venue": venue(),
        "decision": DecisionDetails(decision=choice),
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


@pytest.mark.parametrize(
    "changes",
    [{"slots": []}, {"slots": ["AM", "AM"]}, {"end_date": "2026-10-01"}],
)
def test_invalid_requested_period_cannot_be_assessed(changes):
    with pytest.raises(ValidationError):
        subject(**changes)


@pytest.mark.parametrize(
    "details",
    [
        {"decision": "pending"},
        {"decision": "approved", "reason": "Rejected"},
        {"decision": "approved", "suggested_alternative": "Another venue"},
    ],
)
def test_invalid_decision_details_are_rejected(details):
    with pytest.raises(ValidationError):
        DecisionDetails(**details)


def test_blank_optional_rejection_details_are_absent():
    details = DecisionDetails(
        decision="rejected", reason=" ", suggested_alternative=" "
    )
    assert details.reason is None
    assert details.suggested_alternative is None
