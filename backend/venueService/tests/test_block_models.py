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


def test_partial_block_parses_dates_and_reuses_slot_enum() -> None:
    block = VenueBlockCreate(**payload())
    assert block.start_date == date(2026, 9, 20)
    assert block.end_date == date(2026, 9, 22)
    assert block.slots == [Slot.PM]
    assert block.reason_category is BlockReason.MAINTENANCE
    assert block.reason_detail is None


def test_same_day_full_day_block_uses_chronological_slot_order() -> None:
    block = VenueBlockCreate(
        **payload(end_date="2026-09-20", slots=["NIGHT", "AM", "PM"])
    )
    assert block.start_date == block.end_date
    assert block.model_dump(mode="json")["slots"] == ["AM", "PM", "NIGHT"]


@pytest.mark.parametrize("reason", list(BlockReason))
def test_all_story_reasons_are_accepted(reason: BlockReason) -> None:
    assert VenueBlockCreate(**payload(reason_category=reason)).reason_category is reason


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
)
def test_invalid_input_is_rejected(changes: dict, field: str | None) -> None:
    with pytest.raises(ValidationError) as caught:
        VenueBlockCreate(**payload(**changes))
    if field is not None:
        assert caught.value.errors()[0]["loc"][0] == field


def test_reason_category_is_required() -> None:
    data = payload()
    del data["reason_category"]
    with pytest.raises(ValidationError) as caught:
        VenueBlockCreate(**data)
    assert caught.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize(
    "detail, expected",
    [(None, None), ("   ", None), ("  Repairs  ", "Repairs"), ("x" * 1000, "x" * 1000)],
)
def test_optional_detail_is_normalized(
    detail: str | None, expected: str | None
) -> None:
    assert VenueBlockCreate(**payload(reason_detail=detail)).reason_detail == expected


@pytest.mark.parametrize(
    "field, value",
    [
        ("id", "client-id"),
        ("venue_id", "another-venue"),
        ("created_by", "another-user"),
        ("created_at", "2026-09-01T00:00:00Z"),
        ("status", "lifted"),
    ],
)
def test_creation_rejects_server_owned_fields(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as caught:
        VenueBlockCreate(**payload(**{field: value}))
    assert caught.value.errors()[0]["type"] == "extra_forbidden"


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


@pytest.mark.parametrize("field", ["venue_id", "created_by"])
def test_stored_identity_cannot_be_blank(field: str) -> None:
    data = {**payload(), "venue_id": "venue-1", "created_by": "staff-1"}
    data[field] = "  "
    with pytest.raises(ValidationError):
        VenueBlock(**data)
