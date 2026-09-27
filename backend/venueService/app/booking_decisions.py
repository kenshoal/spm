"""Pure SCRUM-15 decision rules, with no booking storage or API contract.

The models below are internal projections. An eventual adapter must load the
current booking, blocks and confirmed reservations from trusted storage. These
rules neither authorize the caller nor save, reserve, notify or prevent races.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.availability_models import AvailabilityResult, Period
from app.block_checks import check_availability
from app.block_models import VenueBlock
from app.models import Venue
from app.slots import overlaps


class BookingDecisionSubject(Period):
    """Minimal current booking projection; map storage statuses in the adapter."""

    venue_id: str = Field(min_length=1)
    # Only the normalized 'pending' state is eligible. Unknown states fail closed.
    current_status: str = Field(min_length=1)


class ConfirmedVenueBooking(Period):
    """An actual confirmed reservation, irrespective of the parent event status.

    The adapter must omit cancelled/unconfirmed reservations. Proposed event
    timing alone is not evidence of a reserved slot.
    """

    booking_id: str = Field(min_length=1)
    venue_id: str = Field(min_length=1)


class DecisionDetails(BaseModel):
    """A proposed staff decision, not a public HTTP request model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["approved", "rejected"]
    reason: str | None = None
    suggested_alternative: str | None = None

    @field_validator("reason", "suggested_alternative")
    @classmethod
    def blank_is_absent(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def rejection_details_only(self) -> "DecisionDetails":
        if self.decision == "approved" and (
            self.reason is not None or self.suggested_alternative is not None
        ):
            raise ValueError("Reason and suggested alternative belong to rejection")
        return self


RefusalCode = Literal[
    "request_not_pending",
    "venue_mismatch",
    "block_check_unavailable",
    "booking_check_unavailable",
    "venue_unavailable",
    "outside_operating_slots",
    "active_block",
    "booking_conflict",
]


class DecisionAssessment(BaseModel):
    """A result to act on later, never evidence that a decision was saved.

    A refused approval has no target status; keep it pending and record its
    refusal codes/evidence in the eventual audit store. Explicit rejection is
    a separate staff action.
    """

    allowed: bool
    target_status: Literal["approved", "rejected"] | None = None
    refusal_codes: list[RefusalCode] = Field(default_factory=list)
    availability: AvailabilityResult | None = None
    conflicting_booking_ids: list[str] = Field(default_factory=list)
    reason: str | None = None
    suggested_alternative: str | None = None


def assess_booking_decision(
    *,
    booking: BookingDecisionSubject,
    decision: DecisionDetails,
    venue: Venue,
    blocks: Sequence[VenueBlock] | None,
    confirmed_bookings: Sequence[ConfirmedVenueBooking] | None,
) -> DecisionAssessment:
    """Assess a decision using current data, without modifying any input.

    None means a lookup has not succeeded; [] means a successful empty lookup.
    Rejection needs neither availability lookup. Approval needs both. The future
    commit workflow must revalidate these facts under concurrency protection.
    """
    if booking.current_status != "pending":
        return DecisionAssessment(allowed=False, refusal_codes=["request_not_pending"])
    if booking.venue_id != venue.id:
        return DecisionAssessment(allowed=False, refusal_codes=["venue_mismatch"])
    if decision.decision == "rejected":
        return DecisionAssessment(
            allowed=True,
            target_status="rejected",
            reason=decision.reason,
            suggested_alternative=decision.suggested_alternative,
        )

    refusals: list[RefusalCode] = []
    availability = None
    if blocks is None:
        refusals.append("block_check_unavailable")
    else:
        availability = check_availability(venue, booking, blocks)
        refusals.extend(availability.reasons)

    conflicting_ids = []
    if confirmed_bookings is None:
        refusals.append("booking_check_unavailable")
    else:
        conflicting_ids = sorted(
            {
                other.booking_id
                for other in confirmed_bookings
                if other.venue_id == booking.venue_id
                and overlaps(
                    booking.start_date,
                    booking.end_date,
                    booking.slots,
                    other.start_date,
                    other.end_date,
                    other.slots,
                )
            }
        )
        if conflicting_ids:
            refusals.append("booking_conflict")

    return DecisionAssessment(
        allowed=not refusals,
        target_status=None if refusals else "approved",
        refusal_codes=refusals,
        availability=availability,
        conflicting_booking_ids=conflicting_ids,
    )
