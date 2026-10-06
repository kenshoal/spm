from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.block_models import BlockReason, BlockStatus, VenueBlock, VenueBlockCreate
from app.models import Slot


def payload(**changes: object) -> dict:
    return {
        "start_date": "2026-09-20",
        "end_date": "2026-09-22",
        "slots": ["PM"],
        "reason_category": "maintenance",
        **changes,
    }


# AC1-H3 (happy): a valid block request parses its dates and slots
def test_partial_block_parses_dates_and_reuses_slot_enum() -> None:
    block = VenueBlockCreate(**payload())
    assert block.start_date == date(2026, 9, 20)
    assert block.end_date == date(2026, 9, 22)
    assert block.slots == [Slot.PM]
    assert block.reason_category is BlockReason.MAINTENANCE
    assert block.reason_detail is None


# AC1-B4 (boundary): a same-day full-day block keeps AM, PM, NIGHT order
def test_same_day_full_day_block_uses_chronological_slot_order() -> None:
    block = VenueBlockCreate(
        **payload(end_date="2026-09-20", slots=["NIGHT", "AM", "PM"])
    )
    assert block.start_date == block.end_date
    assert block.model_dump(mode="json")["slots"] == ["AM", "PM", "NIGHT"]


# AC1-P6 (partition): each story reason category is accepted by the API model
@pytest.mark.parametrize("reason", list(BlockReason), ids=["AC1-P6a", "AC1-P6b", "AC1-P6c", "AC1-P6d"])
def test_all_story_reasons_are_accepted(reason: BlockReason) -> None:
    assert VenueBlockCreate(**payload(reason_category=reason)).reason_category is reason


# AC1-N10 (negative): invalid dates and slots are rejected before storage
@pytest.mark.parametrize(
    "changes, field",
    [
        ({"end_date": "2026-09-19"}, None),
        ({"start_date": "2026-02-30"}, "start_date"),
        ({"slots": []}, "slots"),
        ({"slots": ["MORNING"]}, "slots"),
        ({"slots": ["AM", "AM"]}, "slots"),
        ({"reason_category": ""}, "reason_category"),
        ({"reason_category": "other"}, "reason_category"),
        ({"reason_detail": "x" * 1001}, "reason_detail"),
    ],
    ids=["AC1-N10a", "AC1-N10b", "AC1-N10c", "AC1-N10d", "AC1-N10e", "AC1-N10f", "AC1-N10g", "AC1-N10h"],
)
def test_invalid_input_is_rejected(changes: dict, field: str | None) -> None:
    with pytest.raises(ValidationError) as caught:
        VenueBlockCreate(**payload(**changes))
    if field is not None:
        assert caught.value.errors()[0]["loc"][0] == field


# AC1-N11 (negative): a block without a reason is rejected
def test_reason_category_is_required() -> None:
    data = payload()
    del data["reason_category"]
    with pytest.raises(ValidationError) as caught:
        VenueBlockCreate(**data)
    assert caught.value.errors()[0]["type"] == "missing"


# AC1-P7 (partition): detail is trimmed, blank becomes absent, 1000 characters are kept
@pytest.mark.parametrize(
    "detail, expected",
    [(None, None), ("   ", None), ("  Repairs  ", "Repairs"), ("x" * 1000, "x" * 1000)],
    ids=["AC1-P7a", "AC1-P7b", "AC1-P7c", "AC1-P7d"],
)
def test_optional_detail_is_normalized(
    detail: str | None, expected: str | None
) -> None:
    assert VenueBlockCreate(**payload(reason_detail=detail)).reason_detail == expected


# AC1-N12 (negative): clients cannot set id, venue, creator, status or timestamp
@pytest.mark.parametrize(
    "field, value",
    [
        ("id", "client-id"),
        ("venue_id", "another-venue"),
        ("created_by", "another-user"),
        ("created_at", "2026-09-01T00:00:00Z"),
        ("status", "lifted"),
    ],
    ids=["AC1-N12a", "AC1-N12b", "AC1-N12c", "AC1-N12d", "AC1-N12e"],
)
def test_creation_rejects_server_owned_fields(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as caught:
        VenueBlockCreate(**payload(**{field: value}))
    assert caught.value.errors()[0]["type"] == "extra_forbidden"


# AC1-H4 (happy): a stored block gets an id, a UTC timestamp and active status
def test_stored_block_adds_identity_and_utc_defaults() -> None:
    request = VenueBlockCreate(**payload())
    before = datetime.now(UTC)
    block = VenueBlock(**request.model_dump(), venue_id="venue-1", created_by="staff-1")
    other = VenueBlock(**request.model_dump(), venue_id="venue-1", created_by="staff-1")
    assert UUID(block.id).version == 4
    assert block.id != other.id
    assert block.venue_id == "venue-1"
    assert block.created_by == "staff-1"
    assert block.status is BlockStatus.ACTIVE
    assert block.created_at.tzinfo is UTC
    assert before <= block.created_at <= datetime.now(UTC)
    assert VenueBlock.model_validate_json(block.model_dump_json()) == block


# AC1-N13 (negative): a stored block needs a venue and a creator
@pytest.mark.parametrize("field", ["venue_id", "created_by"], ids=["AC1-N13a", "AC1-N13b"])
def test_stored_identity_cannot_be_blank(field: str) -> None:
    data = {**payload(), "venue_id": "venue-1", "created_by": "staff-1"}
    data[field] = "  "
    with pytest.raises(ValidationError):
        VenueBlock(**data)
