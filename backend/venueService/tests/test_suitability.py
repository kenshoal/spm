"""Tests for the suitability comparison logic (app/suitability.py)."""

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


def test_attendance_within_capacity_is_suitable() -> None:
    result = check_suitability(
        _venue(max_capacity=100), SuitabilityRequest(expected_attendance=100)
    )

    assert result.suitable is True
    assert result.mismatches == []


def test_attendance_exceeding_capacity_is_not_suitable() -> None:
    result = check_suitability(
        _venue(max_capacity=100), SuitabilityRequest(expected_attendance=101)
    )

    assert result.suitable is False
    assert [m.attribute for m in result.mismatches] == ["capacity"]


def test_missing_required_layout_is_flagged() -> None:
    result = check_suitability(
        _venue(supported_layouts=[RoomLayout.THEATRE]),
        SuitabilityRequest(
            expected_attendance=10, required_layout=RoomLayout.BOARDROOM
        ),
    )

    assert result.suitable is False
    assert [m.attribute for m in result.mismatches] == ["layout"]


def test_missing_required_slot_is_flagged() -> None:
    result = check_suitability(
        _venue(operating_slots=[Slot.AM]),
        SuitabilityRequest(expected_attendance=10, required_slot=Slot.NIGHT),
    )

    assert result.suitable is False
    assert [m.attribute for m in result.mismatches] == ["operating_slot"]


def test_missing_required_facility_is_flagged() -> None:
    result = check_suitability(
        _venue(facilities=["Projector"]),
        SuitabilityRequest(
            expected_attendance=10, required_facilities=["Projector", "Stage"]
        ),
    )

    assert result.suitable is False
    assert [m.attribute for m in result.mismatches] == ["facilities"]
    assert "Stage" in result.mismatches[0].reason


def test_facility_match_is_case_insensitive() -> None:
    result = check_suitability(
        _venue(facilities=["Projector"]),
        SuitabilityRequest(expected_attendance=10, required_facilities=["projector"]),
    )

    assert result.suitable is True


def test_missing_required_accessibility_is_flagged() -> None:
    result = check_suitability(
        _venue(accessibility_features=[]),
        SuitabilityRequest(
            expected_attendance=10, required_accessibility=["Wheelchair ramp"]
        ),
    )

    assert result.suitable is False
    assert [m.attribute for m in result.mismatches] == ["accessibility"]


def test_multiple_mismatches_are_all_reported() -> None:
    result = check_suitability(
        _venue(max_capacity=10, supported_layouts=[], operating_slots=[]),
        SuitabilityRequest(
            expected_attendance=50,
            required_layout=RoomLayout.THEATRE,
            required_slot=Slot.AM,
        ),
    )

    assert result.suitable is False
    assert {m.attribute for m in result.mismatches} == {
        "capacity",
        "layout",
        "operating_slot",
    }


def test_no_requirements_beyond_attendance_is_suitable() -> None:
    result = check_suitability(_venue(), SuitabilityRequest(expected_attendance=1))

    assert result.suitable is True
    assert result.mismatches == []
