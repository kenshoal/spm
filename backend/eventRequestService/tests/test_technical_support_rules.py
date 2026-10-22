"""Unit rules for technical support requirements and assignments (SCRUM-19).

Case IDs refer to docs/testcases/scrum_19_testcases.md. The fake rows below
mirror what the repository returns, so group_by_requirement is exercised on
realistic shapes.
"""

import pytest
from pydantic import ValidationError

from app.models.technical_support import (
    AssignmentCreate,
    RequirementCreate,
    SkillTag,
)
from app.services.technical_support_rules import (
    SupportNotAllowedError,
    ensure_support_allowed,
    group_by_requirement,
    is_suitable,
)

EVENT_ID = "11111111-1111-4111-8111-111111111111"
REQ_AV = "aaaa0000-0000-4000-8000-000000000001"
REQ_IT = "aaaa0000-0000-4000-8000-000000000002"


def requirement_row(
    requirement_id: str = REQ_AV,
    recorded_at: str = "2030-03-01T09:00:00+00:00",
) -> dict[str, object]:
    return {
        "id": requirement_id,
        "event_request_id": EVENT_ID,
        "description": "Two wireless mics for the keynote",
        "skill_tag": "audio_visual",
        "recorded_by": "coord-1",
        "recorded_at": recorded_at,
    }


def assignment_row(
    requirement_id: str = REQ_AV,
    staff_id: str = "tss-av",
    assigned_at: str = "2030-03-01T10:00:00+00:00",
    assignment_id: str = "bbbb0000-0000-4000-8000-000000000001",
) -> dict[str, object]:
    return {
        "id": assignment_id,
        "requirement_id": requirement_id,
        "event_request_id": EVENT_ID,
        "staff_id": staff_id,
        "assigned_by": "coord-1",
        "assigned_at": assigned_at,
    }


# AC1-P1, AC1-P2, AC1-P3 (partition): each allowed status accepts support work
@pytest.mark.parametrize(
    "status",
    ["Approved", "Planning", "Confirmed"],
    ids=["AC1-P1", "AC1-P2", "AC1-P3"],
)
def test_allowed_statuses_accept_support(status: str) -> None:
    ensure_support_allowed(status)


# AC1-P4..P10 (partition): every other status refuses, including the terminal ones
@pytest.mark.parametrize(
    "status",
    [
        "Draft",
        "Submitted",
        "Under Review",
        "Changes Requested",
        "Rejected",
        "Completed",
        "Cancelled",
    ],
    ids=[
        "AC1-P4",
        "AC1-P5",
        "AC1-P6",
        "AC1-P7",
        "AC1-P8",
        "AC1-P9",
        "AC1-P10",
    ],
)
def test_other_statuses_refuse_support(status: str) -> None:
    with pytest.raises(SupportNotAllowedError):
        ensure_support_allowed(status)


# AC1-P11, AC1-P12, AC1-P13, AC1-P14 (partition): each tag in the vocabulary is accepted
@pytest.mark.parametrize(
    "skill_tag",
    ["audio_visual", "lighting", "it_network", "livestream"],
    ids=["AC1-P11", "AC1-P12", "AC1-P13", "AC1-P14"],
)
def test_each_skill_tag_is_accepted(skill_tag: str) -> None:
    parsed = RequirementCreate(description="Mics", skill_tag=skill_tag)

    assert parsed.skill_tag == SkillTag(skill_tag)
    assert parsed.description == "Mics"


# AC1-N2 (negative): tags are case-sensitive, so wrong casing is not a tag
def test_skill_tag_is_case_sensitive() -> None:
    with pytest.raises(ValidationError):
        RequirementCreate(description="Mics", skill_tag="Audio_Visual")


# AC1-B1 (boundary): an empty description is refused
def test_empty_description_is_refused() -> None:
    with pytest.raises(ValidationError):
        RequirementCreate(description="", skill_tag="audio_visual")


# AC1-B2 (boundary): a whitespace-only description is refused, not stored blank
def test_whitespace_description_is_refused() -> None:
    with pytest.raises(ValidationError):
        RequirementCreate(description="   \n\t", skill_tag="audio_visual")


# AC1-B3 (boundary): the shortest valid description is stored as sent
def test_shortest_valid_description() -> None:
    parsed = RequirementCreate(description="A", skill_tag="audio_visual")

    assert parsed.description == "A"


# AC1-B4 (boundary): a description of exactly 2000 characters is accepted
def test_description_at_the_limit_is_accepted() -> None:
    parsed = RequirementCreate(description="x" * 2000, skill_tag="audio_visual")

    assert len(parsed.description) == 2000


# AC1-B5 (boundary): one character over the limit is refused
def test_description_over_the_limit_is_refused() -> None:
    with pytest.raises(ValidationError):
        RequirementCreate(description="x" * 2001, skill_tag="audio_visual")


# AC3-P1 (partition): role and a matching tag make a person suitable
def test_role_and_matching_tag_is_suitable() -> None:
    assert is_suitable(("technical_support",), {"audio_visual"}, "audio_visual")


# AC3-P2 (partition): the role with a different tag is not suitable
def test_role_with_wrong_tag_is_not_suitable() -> None:
    assert is_suitable(("technical_support",), {"lighting"}, "audio_visual") is False


# AC3-P3 (partition): the role with no tags is not suitable
def test_role_without_tags_is_not_suitable() -> None:
    assert is_suitable(("technical_support",), set(), "audio_visual") is False


# AC3-P4 (partition): the tag without the technical_support role is not suitable
def test_tag_without_role_is_not_suitable() -> None:
    assert is_suitable(("venue_staff",), {"audio_visual"}, "audio_visual") is False


# AC3-X2 (cross-cutting): a multi-tag staff member is suitable for each of their
# tags and only those — the rule reads the requirement's tag, not a constant
def test_multi_tag_staff_suitable_exactly_for_their_tags() -> None:
    roles = ("technical_support",)
    tags = {"audio_visual", "it_network"}

    assert is_suitable(roles, tags, "audio_visual")
    assert is_suitable(roles, tags, "it_network")
    assert is_suitable(roles, tags, "lighting") is False
    assert is_suitable(roles, tags, "livestream") is False


# AC4-P2 (partition): assignments land under their own requirement only
def test_assignments_group_under_their_own_requirement() -> None:
    requirements = [requirement_row(REQ_AV), requirement_row(REQ_IT)]
    assignments = [
        assignment_row(REQ_AV, "tss-av"),
        assignment_row(REQ_AV, "tss-av2", assignment_id="bbbb0000-0000-4000-8000-000000000002"),
        assignment_row(REQ_IT, "tss-av", assignment_id="bbbb0000-0000-4000-8000-000000000003"),
    ]

    grouped = group_by_requirement(requirements, assignments)

    grouped_staff = {
        row["id"]: [member["staff_id"] for member in staff]
        for row, staff in grouped
    }
    assert grouped_staff[REQ_AV] == ["tss-av", "tss-av2"]
    assert grouped_staff[REQ_IT] == ["tss-av"]


# AC4-P1 (partition, grouping half): a requirement nobody is on shows an empty list
def test_requirement_without_assignments_groups_empty() -> None:
    grouped = group_by_requirement([requirement_row(REQ_AV)], [])

    assert grouped[0][1] == []


# AC4-B1 (boundary): equal timestamps fall back to ids, so the order is stable —
# requirements by (recorded_at, id), staff by (assigned_at, assignment id)
def test_ordering_falls_back_to_ids_when_timestamps_tie() -> None:
    same_time = "2030-03-01T09:00:00+00:00"
    requirements = [
        requirement_row(
            "aaaa0000-0000-4000-8000-000000000002", recorded_at=same_time
        ),
        requirement_row(
            "aaaa0000-0000-4000-8000-000000000001", recorded_at=same_time
        ),
    ]
    # The later staff id holds the smaller assignment id: the tiebreak is the
    # assignment id, matching the repository's ORDER BY assigned_at, id.
    assignments = [
        assignment_row(
            "aaaa0000-0000-4000-8000-000000000001",
            "tss-av2",
            assigned_at=same_time,
            assignment_id="bbbb0000-0000-4000-8000-000000000001",
        ),
        assignment_row(
            "aaaa0000-0000-4000-8000-000000000001",
            "tss-av",
            assigned_at=same_time,
            assignment_id="bbbb0000-0000-4000-8000-000000000002",
        ),
    ]

    grouped = group_by_requirement(requirements, assignments)

    assert [row["id"] for row, _ in grouped] == [
        "aaaa0000-0000-4000-8000-000000000001",
        "aaaa0000-0000-4000-8000-000000000002",
    ]
    assert [member["staff_id"] for member in grouped[0][1]] == ["tss-av2", "tss-av"]


# AC2-B1..B3 (boundary, request half): staff_id length is validated at the edge —
# blank refused, exactly 64 characters accepted for checking, 65 refused
@pytest.mark.parametrize(
    ("staff_id", "valid"),
    [("", False), ("s" * 64, True), ("s" * 65, False)],
    ids=["AC2-B1", "AC2-B2", "AC2-B3"],
)
def test_staff_id_length_boundaries(staff_id: str, valid: bool) -> None:
    if valid:
        assert AssignmentCreate(staff_id=staff_id).staff_id == staff_id
    else:
        with pytest.raises(ValidationError):
            AssignmentCreate(staff_id=staff_id)
