"""Pure SCRUM-15 decision rules, with no booking storage or API contract.

The models below are internal projections. An eventual adapter must load the
current booking, blocks and confirmed reservations from trusted storage. These
rules neither authorize the caller nor save, reserve, notify or prevent races.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.availability_models import AvailabilityResult, Period
from app.block_checks import check_availability
from app.block_models import VenueBlock
from app.hold_models import VenueHold
from app.models import Slot, Venue
from app.slots import check_time_range, slots_to_range, times_overlap
from app.time_conflicts import padded_range, window_refusals


class _TimedPeriod(BaseModel):
    """A date range with its daily time range (SCRUM-65). Without times, the
    consecutive slots give the range, as the 0050 conversion does."""

    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    start_minute: int | None = None
    end_minute: int | None = None
    slots: list[Slot] = Field(default_factory=list)

    @model_validator(mode="after")
    def _default_times(self) -> "_TimedPeriod":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.start_minute is None or self.end_minute is None:
            self.start_minute, self.end_minute = slots_to_range(self.slots)
        check_time_range(self.start_minute, self.end_minute)
        return self

    def period(self) -> Period:
        return Period(
            start_date=self.start_date, end_date=self.end_date,
            start_minute=self.start_minute, end_minute=self.end_minute,
        )


class BookingDecisionSubject(_TimedPeriod):
    """Minimal current booking projection; map storage statuses in the adapter."""

    venue_id: str = Field(min_length=1)
    # Only the normalized 'pending' state is eligible. Unknown states fail closed.
    current_status: str = Field(min_length=1)


class ConfirmedVenueBooking(_TimedPeriod):
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
        if self.decision == "rejected" and self.reason is None:
            raise ValueError("A rejection needs a reason")
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
    "setup_outside_window",
    "turnaround_outside_window",
    "booking_conflict",
    "hold_conflict",
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
    conflicting_hold_ids: list[str] = Field(default_factory=list)
    reason: str | None = None
    suggested_alternative: str | None = None


def assess_booking_decision(
    *,
    booking: BookingDecisionSubject,
    decision: DecisionDetails,
    venue: Venue,
    blocks: Sequence[VenueBlock] | None,
    confirmed_bookings: Sequence[ConfirmedVenueBooking] | None,
    holds: Sequence[VenueHold] = (),
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
        availability = check_availability(venue, booking.period(), blocks)
        refusals.extend(availability.reasons)

    # SCRUM-20: setup and turnaround pad both bookings and must stay in the window.
    # The availability check reports the window codes too (SCRUM-66); add each once.
    setup, turnaround = venue.setup_minutes, venue.turnaround_minutes
    start, end = padded_range(booking.start_minute, booking.end_minute, setup, turnaround)
    for code in window_refusals(booking.start_minute, booking.end_minute, setup, turnaround):
        if code not in refusals:
            refusals.append(code)

    conflicting_ids = []
    if confirmed_bookings is None:
        refusals.append("booking_check_unavailable")
    else:
        conflicting_ids = sorted(
            {
                other.booking_id
                for other in confirmed_bookings
                if other.venue_id == booking.venue_id
                and times_overlap(
                    booking.start_date,
                    booking.end_date,
                    start,
                    end,
                    other.start_date,
                    other.end_date,
                    *padded_range(other.start_minute, other.end_minute, setup, turnaround),
                )
            }
        )
        if conflicting_ids:
            refusals.append("booking_conflict")

    # SCRUM-18: holds that still protect their time refuse it like bookings do;
    # the caller leaves out the request's own event's holds (0066).
    now = datetime.now(UTC)
    hold_ids = sorted(
        hold.id
        for hold in holds
        if hold.venue_id == booking.venue_id
        and hold.protects(now)
        and times_overlap(
            booking.start_date,
            booking.end_date,
            start,
            end,
            hold.start_date,
            hold.end_date,
            *padded_range(hold.start_minute, hold.end_minute, setup, turnaround),
        )
    )
    if hold_ids:
        refusals.append("hold_conflict")

    return DecisionAssessment(
        allowed=not refusals,
        target_status=None if refusals else "approved",
        refusal_codes=refusals,
        availability=availability,
        conflicting_booking_ids=conflicting_ids,
        conflicting_hold_ids=hold_ids,
    )
