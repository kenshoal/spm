"""Suitability comparison: an event's requirements against a venue's record.

Pure and side-effect free — it never books, holds, or updates a venue; the
router that calls this is the only place that touches storage.
"""

from __future__ import annotations

from app.models import Venue
from app.suitability_models import (
    SuitabilityMismatch,
    SuitabilityRequest,
    SuitabilityResult,
)


def check_suitability(venue: Venue, request: SuitabilityRequest) -> SuitabilityResult:
    mismatches: list[SuitabilityMismatch] = []

    # Q&A #112: judged by the chosen layout's own capacity when it has one.
    capacity = venue.capacity_for(request.required_layout)
    if request.expected_attendance > capacity:
        mismatches.append(
            SuitabilityMismatch(
                attribute="capacity",
                reason=(
                    f"Venue capacity ({capacity}) is below the expected "
                    f"attendance ({request.expected_attendance})."
                ),
            )
        )

    if (
        request.required_layout is not None
        and request.required_layout not in venue.supported_layouts
    ):
        mismatches.append(
            SuitabilityMismatch(
                attribute="layout",
                reason=f"Venue does not support the {request.required_layout.value} layout.",
            )
        )

    venue_facilities = {facility.lower() for facility in venue.facilities}
    missing_facilities = [
        facility
        for facility in request.required_facilities
        if facility.lower() not in venue_facilities
    ]
    if missing_facilities:
        mismatches.append(
            SuitabilityMismatch(
                attribute="facilities",
                reason=f"Venue does not provide: {', '.join(missing_facilities)}.",
            )
        )

    venue_accessibility = {feature.lower() for feature in venue.accessibility_features}
    missing_accessibility = [
        feature
        for feature in request.required_accessibility
        if feature.lower() not in venue_accessibility
    ]
    if missing_accessibility:
        mismatches.append(
            SuitabilityMismatch(
                attribute="accessibility",
                reason=f"Venue does not provide: {', '.join(missing_accessibility)}.",
            )
        )

    # SCRUM-30 AC5, SCRUM-12 AC3: a requested time must lie inside the venue's operating hours.
    start, end = request.required_start_minute, request.required_end_minute
    if start is not None and end is not None and not venue.is_open_for(start, end):
        mismatches.append(
            SuitabilityMismatch(
                attribute="operating_hours",
                reason=(
                    f"Venue operates {_clock(venue.operating_start_minute)} to "
                    f"{_clock(venue.operating_end_minute)}, outside the requested "
                    f"{_clock(start)} to {_clock(end)}."
                ),
            )
        )

    return SuitabilityResult(
        venue_id=venue.id, suitable=not mismatches, mismatches=mismatches
    )


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"
