"""Live schema tests against the Supabase `venues` / `venue_blocks` tables.

These are integration tests, not unit tests: they make real requests to a
live Supabase project's REST API (PostgREST) and verify the schema created by
hand in the SQL Editor actually behaves as designed — the expected columns
exist, the enums reject invalid values, and the foreign key from
`venue_blocks.venue_id` to `venues.id` is enforced.

`venue_blocks` is aligned to the `VenueBlock` / `VenueBlockCreate` Pydantic
models in `app/block_models.py` (feat/venue-blocking): `slots` is a mandatory
non-empty array, `reason_category` is a closed enum with an optional
`reason_detail` free-text field, and `status` is an explicit ACTIVE/LIFTED
enum rather than a nullable "released" timestamp.

They deliberately do NOT run unless SUPABASE_URL and SUPABASE_SECRET_KEY are
set in the environment, so:
  * CI (which has no Supabase secret configured) never fails on these.
  * No credential is ever hardcoded here — set them locally, e.g. from the
    project's .env, before running: `pytest tests/test_supabase_schema.py`.

The secret key is used (not the publishable key) so these bypass Row Level
Security entirely and are testing the schema itself, not a policy.

Every test either performs no write at all (it's a negative/rejected write)
or cleans up any row it created in a `finally` block, so the live table is
left exactly as it found it either way.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import pytest

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

pytestmark = pytest.mark.skipif(
    not SUPABASE_URL or not SUPABASE_SECRET_KEY,
    reason="set SUPABASE_URL and SUPABASE_SECRET_KEY to run live schema tests",
)


def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    prefer: str | None = None,
) -> tuple[int, Any]:
    """Minimal PostgREST call. Returns (status_code, parsed_json_or_None)."""

    url = f"{SUPABASE_URL}/rest/v1/{path}"
    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data = json.dumps(json_body).encode() if json_body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as error:
        body = error.read().decode()
        return error.code, (json.loads(body) if body else None)


def _valid_block_payload(venue_id: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "venue_id": venue_id,
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "slots": ["AM", "PM"],
        "reason_category": "maintenance",
    }
    payload.update(overrides)
    return payload


def test_venues_table_has_expected_columns() -> None:
    status, body = _request(
        "GET",
        "venues?select=id,name,location,max_capacity,facilities,"
        "accessibility_features,supported_layouts,operating_slots,status,"
        "created_at,updated_at&limit=1",
    )

    assert status == 200
    assert isinstance(body, list)


def test_venue_status_enum_rejects_invalid_value() -> None:
    status, body = _request(
        "POST",
        "venues",
        json_body={
            "name": "schema check",
            "location": "nowhere",
            "max_capacity": 10,
            "status": "NOT_A_STATUS",
        },
        prefer="return=minimal",
    )

    assert status == 400
    assert "venue_status" in body["message"]


def test_venue_blocks_table_has_expected_columns() -> None:
    status, body = _request(
        "GET",
        "venue_blocks?select=id,venue_id,start_date,end_date,slots,"
        "reason_category,reason_detail,created_by,created_at,status&limit=1",
    )

    assert status == 200
    assert isinstance(body, list)


def test_booking_slot_enum_rejects_invalid_value() -> None:
    status, body = _request(
        "POST",
        "venue_blocks",
        json_body=_valid_block_payload(
            "00000000-0000-0000-0000-000000000000",
            slots=["NOT_A_REAL_SLOT"],
        ),
        prefer="return=minimal",
    )

    assert status == 400
    assert "booking_slot" in body["message"]


def test_duplicate_slots_are_rejected() -> None:
    status, body = _request(
        "POST",
        "venue_blocks",
        json_body=_valid_block_payload(
            "00000000-0000-0000-0000-000000000000",
            slots=["AM", "AM"],
        ),
        prefer="return=minimal",
    )

    assert status == 400
    assert body["code"] == "23514"  # check_violation


def test_null_slot_element_is_rejected() -> None:
    status, body = _request(
        "POST",
        "venue_blocks",
        json_body=_valid_block_payload(
            "00000000-0000-0000-0000-000000000000",
            slots=[None],
        ),
        prefer="return=minimal",
    )

    assert status == 400
    assert body["code"] == "23514"  # check_violation


def test_block_reason_enum_rejects_invalid_value() -> None:
    status, body = _request(
        "POST",
        "venue_blocks",
        json_body=_valid_block_payload(
            "00000000-0000-0000-0000-000000000000",
            reason_category="weather",
        ),
        prefer="return=minimal",
    )

    assert status == 400
    assert "block_reason" in body["message"]


def test_reason_detail_length_limit_is_enforced() -> None:
    status, body = _request(
        "POST",
        "venue_blocks",
        json_body=_valid_block_payload(
            "00000000-0000-0000-0000-000000000000",
            reason_detail="x" * 1001,
        ),
        prefer="return=minimal",
    )

    assert status == 400
    assert body["code"] == "23514"  # check_violation


def test_venue_blocks_rejects_nonexistent_venue_id() -> None:
    status, body = _request(
        "POST",
        "venue_blocks",
        json_body=_valid_block_payload("11111111-1111-1111-1111-111111111111"),
        prefer="return=minimal",
    )

    assert status == 409
    assert body["code"] == "23503"


def test_create_venue_and_block_round_trip() -> None:
    """Positive path: a real venue can hold a real block; both are cleaned up."""

    status, created_venues = _request(
        "POST",
        "venues",
        json_body={
            "name": "Integration Test Hall",
            "location": "Test Location",
            "max_capacity": 50,
        },
        prefer="return=representation",
    )
    assert status == 201
    venue_id = created_venues[0]["id"]

    try:
        status, created_blocks = _request(
            "POST",
            "venue_blocks",
            json_body=_valid_block_payload(
                venue_id, reason_detail="integration test block"
            ),
            prefer="return=representation",
        )
        assert status == 201
        block = created_blocks[0]
        assert block["venue_id"] == venue_id
        assert block["slots"] == ["AM", "PM"]
        assert block["reason_category"] == "maintenance"
        assert block["status"] == "active"

        status, _ = _request("DELETE", f"venue_blocks?id=eq.{block['id']}")
        assert status == 204
    finally:
        _request("DELETE", f"venues?id=eq.{venue_id}")
