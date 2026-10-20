"""Tests for the suitability comparison logic (app/suitability.py).

Every test carries its case ID from docs/testcases/scrum_12_testcases.md.
"""

import pytest
from time_support import slot_times

from app.models import RoomLayout, Slot, Venue
from app.suitability import check_suitability
from app.suitability_models import SuitabilityRequest


def _venue(**overrides: object) -> Venue:
    defaults: dict[str, object] = {
        "name": "Orchard Hall",
        "location": "Orchard Road",
        "max_capacity": 100,
        "facilities": ["Projector", "Microphone"],
        "accessibility_features": ["Wheelchair ramp"],
        "supported_layouts": [RoomLayout.THEATRE, RoomLayout.CLASSROOM],
        "operating_slots": [Slot.AM, Slot.PM],
    }
    defaults.update(overrides)
    return Venue(**defaults)


def _attributes(result) -> list[str]:
    return [mismatch.attribute for mismatch in result.mismatches]


# AC1-B1, AC1-B2, AC1-B3 (boundary): capacity is exceeded only above the maximum
@pytest.mark.parametrize(
    ("attendance", "expected_attributes"),
    [(99, []), (100, []), (101, ["capacity"])],
    ids=["AC1-B1", "AC1-B2", "AC1-B3"],
)
def test_capacity_is_exceeded_only_above_the_maximum(
    attendance: int, expected_attributes: list[str]
) -> None:
    result = check_suitability(
        _venue(max_capacity=100), SuitabilityRequest(expected_attendance=attendance)
    )

    assert _attributes(result) == expected_attributes
    assert result.suitable is (not expected_attributes)


# AC2-N1 (negative): flags the missing facility and names only that one
def test_only_the_missing_facility_is_named() -> None:
    result = check_suitability(
        _venue(facilities=["Projector"]),
        SuitabilityRequest(
            expected_attendance=10, required_facilities=["Projector", "Stage"]
        ),
    )

    assert result.suitable is False
    assert _attributes(result) == ["facilities"]
    assert "Stage" in result.mismatches[0].reason
    assert "Projector" not in result.mismatches[0].reason


# AC2-P1, AC2-P2 (partition): a provided facility matches whichever side differs in case
@pytest.mark.parametrize(
    ("venue_has", "event_requires"),
    [("Projector", "projector"), ("projector", "PROJECTOR")],
    ids=["AC2-P1", "AC2-P2"],
)
def test_facility_match_ignores_letter_case(
    venue_has: str, event_requires: str
) -> None:
    result = check_suitability(
        _venue(facilities=[venue_has]),
        SuitabilityRequest(
            expected_attendance=10, required_facilities=[event_requires]
        ),
    )

    assert result.suitable is True
    assert result.mismatches == []


# AC3-H1 (happy): a venue meeting every requirement is suitable with no mismatches
def test_venue_meeting_every_requirement_is_suitable() -> None:
    result = check_suitability(
        _venue(),
        SuitabilityRequest(
            expected_attendance=100,
            required_layout=RoomLayout.THEATRE,
            required_start_minute=720,
            required_end_minute=1080,
            required_facilities=["Projector", "Microphone"],
            required_accessibility=["Wheelchair ramp"],
        ),
    )

    assert result.suitable is True
    assert result.mismatches == []


# AC3-P1, AC3-P2, AC3-P3, AC3-P4, AC3-P5 (partition): each layout the venue lacks is flagged
@pytest.mark.parametrize(
    "layout",
    list(RoomLayout),
    ids=["AC3-P1", "AC3-P2", "AC3-P3", "AC3-P4", "AC3-P5"],
)
def test_unsupported_layout_is_flagged(layout: RoomLayout) -> None:
    result = check_suitability(
        _venue(supported_layouts=[]),
        SuitabilityRequest(expected_attendance=10, required_layout=layout),
    )

    assert result.suitable is False
    assert _attributes(result) == ["layout"]


# AC3-P6, AC3-P7, AC3-P8 (partition): each old slot's time is inside the fixed
# 07:00-24:00 window every venue operates, so none is flagged (SCRUM-65 AC7;
# the per-venue operating slots are retired, and a time outside the window is
# refused with 422 instead)
@pytest.mark.parametrize(
    "slot",
    list(Slot),
    ids=["AC3-P6", "AC3-P7", "AC3-P8"],
)
def test_slot_outside_operating_slots_is_flagged(slot: Slot) -> None:
    result = check_suitability(
        _venue(operating_slots=[]),
        SuitabilityRequest(
            expected_attendance=10,
            required_start_minute=slot_times([slot])["start_minute"],
            required_end_minute=slot_times([slot])["end_minute"],
        ),
    )

    assert result.suitable is True
    assert result.mismatches == []


# AC3-P9 (partition): an accessibility feature the venue lacks is flagged
def test_missing_accessibility_feature_is_flagged() -> None:
    result = check_suitability(
        _venue(accessibility_features=[]),
        SuitabilityRequest(
            expected_attendance=10, required_accessibility=["Wheelchair ramp"]
        ),
    )

    assert result.suitable is False
    assert _attributes(result) == ["accessibility"]


# AC3-P10, AC3-P11 (partition): a provided accessibility feature matches whichever side differs in case
@pytest.mark.parametrize(
    ("venue_has", "event_requires"),
    [("Wheelchair ramp", "wheelchair ramp"), ("wheelchair ramp", "WHEELCHAIR RAMP")],
    ids=["AC3-P10", "AC3-P11"],
)
def test_accessibility_match_ignores_letter_case(
    venue_has: str, event_requires: str
) -> None:
    result = check_suitability(
        _venue(accessibility_features=[venue_has]),
        SuitabilityRequest(
            expected_attendance=10, required_accessibility=[event_requires]
        ),
    )

    assert result.suitable is True
    assert result.mismatches == []


# AC3-B1 (boundary): with no optional requirements only attendance is compared
def test_no_optional_requirements_compares_attendance_only() -> None:
    result = check_suitability(
        _venue(
            facilities=[],
            accessibility_features=[],
            supported_layouts=[],
            operating_slots=[],
        ),
        SuitabilityRequest(expected_attendance=1),
    )

    assert result.suitable is True
    assert result.mismatches == []


# AC3-X1 (cross-cutting): every unmet attribute is reported together, each once
# (operating slots retired by SCRUM-65)
def test_all_unmet_attributes_are_reported_once() -> None:
    result = check_suitability(
        _venue(
            max_capacity=10,
            facilities=[],
            accessibility_features=[],
            supported_layouts=[],
            operating_slots=[],
        ),
        SuitabilityRequest(
            expected_attendance=50,
            required_layout=RoomLayout.THEATRE,
            required_start_minute=420,
            required_end_minute=720,
            required_facilities=["Stage"],
            required_accessibility=["Hearing loop"],
        ),
    )

    assert result.suitable is False
    assert sorted(_attributes(result)) == [
        "accessibility",
        "capacity",
        "facilities",
        "layout",
    ]


# AC4-H3 (happy): each mismatch reason names the values that failed
def test_reasons_name_the_failing_values() -> None:
    result = check_suitability(
        _venue(
            max_capacity=10,
            facilities=[],
            accessibility_features=[],
            supported_layouts=[],
            operating_slots=[],
        ),
        SuitabilityRequest(
            expected_attendance=50,
            required_layout=RoomLayout.BOARDROOM,
            required_facilities=["Stage"],
            required_accessibility=["Hearing loop"],
        ),
    )

    reasons = {mismatch.attribute: mismatch.reason for mismatch in result.mismatches}
    assert "10" in reasons["capacity"] and "50" in reasons["capacity"]
    assert "boardroom" in reasons["layout"]
    assert "Stage" in reasons["facilities"]
    assert "Hearing loop" in reasons["accessibility"]
