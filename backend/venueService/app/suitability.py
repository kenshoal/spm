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

    if request.expected_attendance > venue.max_capacity:
        mismatches.append(
            SuitabilityMismatch(
                attribute="capacity",
                reason=(
                    f"Venue capacity ({venue.max_capacity}) is below the expected "
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

    return SuitabilityResult(
        venue_id=venue.id, suitable=not mismatches, mismatches=mismatches
    )
