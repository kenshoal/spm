"""Hotfix 12 (Q&A #112): capacity per room layout."""

import pytest
from pydantic import ValidationError

from app.models import RoomLayout, Venue, VenueCreate, VenueUpdate
from app.suitability import check_suitability
from app.suitability_models import SuitabilityRequest

THEATRE = RoomLayout("theatre")
CLASSROOM = RoomLayout("classroom")


def venue() -> Venue:
    return Venue(
        name="Hall",
        location="Marina",
        max_capacity=200,
        supported_layouts=[THEATRE, CLASSROOM],
        layout_capacities={CLASSROOM: 80},
    )


def capacity_mismatches(attendance: int, layout: RoomLayout | None) -> list[str]:
    result = check_suitability(
        venue(), SuitabilityRequest(expected_attendance=attendance, required_layout=layout)
    )
    return [m.reason for m in result.mismatches if m.attribute == "capacity"]


# AC12-H1 (happy): the chosen layout's capacity decides suitability, not the maximum
def test_suitability_uses_the_layout_capacity() -> None:
    assert capacity_mismatches(100, CLASSROOM) == [
        "Venue capacity (80) is below the expected attendance (100)."
    ]


# AC12-B1, AC12-B2 (boundary): exactly the layout's capacity fits, one more does not
@pytest.mark.parametrize(
    ("attendance", "fits"), [(80, True), (81, False)], ids=["AC12-B1", "AC12-B2"]
)
def test_layout_capacity_boundary(attendance: int, fits: bool) -> None:
    assert (capacity_mismatches(attendance, CLASSROOM) == []) is fits


# AC12-P1 (partition): a layout with no recorded capacity falls back to the maximum
def test_layout_without_a_capacity_uses_the_maximum() -> None:
    assert capacity_mismatches(150, THEATRE) == []


# AC12-P2 (partition): with no layout chosen the maximum applies
def test_no_layout_uses_the_maximum() -> None:
    assert capacity_mismatches(150, None) == []


# AC12-N1 (negative): a capacity of zero or below is refused on create and update
@pytest.mark.parametrize("capacity", [0, -1], ids=["zero", "negative"])
def test_non_positive_layout_capacity_is_refused(capacity: int) -> None:
    with pytest.raises(ValidationError):
        VenueCreate(name="H", location="M", max_capacity=10, layout_capacities={THEATRE: capacity})
    with pytest.raises(ValidationError):
        VenueUpdate(layout_capacities={THEATRE: capacity})
