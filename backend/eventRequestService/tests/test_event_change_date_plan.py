"""Pure SCRUM-35 date mapping only: no decision, conflict check or persistence."""

from copy import deepcopy

import pytest

from app.services.event_change_date_plan import (
    DateReschedulePlanError,
    plan_date_only_reschedule,
)

OLD = ["2026-11-20T10:00:00+08:00", "2026-11-22T15:00:00+08:00"]
NEW = ["2026-11-22T10:00:00+08:00", "2026-11-24T15:00:00+08:00"]


def bookings():
    return [
        {
            "id": "pending-booking", "event_request_id": "event-35", "venue_id": "venue-A",
            "start_date": "2026-11-19", "end_date": "2026-11-20",
            "start_minute": 600, "end_minute": 720, "status": "pending",
            "requested_by": "current-coordinator", "metadata": {"notes": ["retain pending evidence"]},
        },
        {
            "id": "approved-booking", "event_request_id": "event-35", "venue_id": "venue-B",
            "start_date": "2026-11-20", "end_date": "2026-11-23",
            "start_minute": 900, "end_minute": 1080, "status": "approved",
            "decided_by": "venue-staff", "decided_at": "2026-10-21T03:00:00Z",
            "metadata": {"notes": ["retain approval evidence"]},
        },
        {"id": "cancelled-booking", "start_date": "2026-11-20", "end_date": "2026-11-21", "start_minute": 600, "end_minute": 720, "status": "cancelled"},
        {"id": "rejected-booking", "start_date": "2026-11-20", "end_date": "2026-11-21", "start_minute": 600, "end_minute": 720, "status": "rejected"},
    ]


def assert_refused(old, new, code):
    rows = bookings()
    protected = deepcopy((old, new, rows))
    with pytest.raises(DateReschedulePlanError) as caught:
        plan_date_only_reschedule(old, new, rows)
    assert isinstance(caught.value, ValueError)
    assert caught.value.code == code
    assert (old, new, rows) == protected


# AC3-H2 (happy): every eligible booking keeps its own range and audit while both dates shift uniformly and excluded statuses remain untouched.
def test_uniform_shift_preserves_complete_rows_order_and_protected_inputs():
    old, new, rows = deepcopy(OLD), deepcopy(NEW), bookings()
    protected = deepcopy((old, new, rows))
    expected = [
        {**deepcopy(rows[0]), "start_date": "2026-11-21", "end_date": "2026-11-22"},
        {**deepcopy(rows[1]), "start_date": "2026-11-22", "end_date": "2026-11-25"},
    ]
    result = plan_date_only_reschedule(old, new, rows)
    assert result == expected
    assert (old, new, rows) == protected
    result[0]["metadata"]["notes"].append("edit the returned preview only")
    assert (old, new, rows) == protected, "Returned rows must be deep copies, including nested evidence"


# AC3-P2 (partition): mixed ISO offsets near midnight must preserve Singapore wall time and use the Singapore calendar delta.
def test_offset_representation_uses_singapore_dates_not_raw_iso_dates():
    old = ["2026-11-20T16:30:00Z"]
    new = ["2026-11-23T00:30:00+08:00"]
    rows = [bookings()[1]]
    protected = deepcopy((old, new, rows))
    assert plan_date_only_reschedule(old, new, rows) == [
        {**deepcopy(rows[0]), "start_date": "2026-11-22", "end_date": "2026-11-25"},
    ]
    assert (old, new, rows) == protected


@pytest.mark.parametrize(
    "new",
    [
        [NEW[0]],
        [NEW[0], "2026-11-24T16:00:00+08:00"],
        [NEW[0], "2026-11-25T15:00:00+08:00"],
        list(reversed(NEW)),
    ],
    ids=["AC3-N5", "AC3-N6", "AC3-N7", "AC3-N8"],
)
# AC3-N5, AC3-N6, AC3-N7, AC3-N8 (negative): incomplete, time-changing, nonuniform or reordered anchors cannot yield a guessed partial mapping.
def test_inconsistent_mapping_refuses_before_any_input_changes(new):
    assert_refused(deepcopy(OLD), deepcopy(new), "unsupported_date_mapping")


@pytest.mark.parametrize(
    ("old", "new"),
    [([], []), (OLD, ["not-a-time", NEW[1]])],
    ids=["AC3-N9", "AC3-N10"],
)
# AC3-N9, AC3-N10 (negative): absent or unparsable anchors must use the explicit refusal contract instead of an empty plan or leaked parser error.
def test_invalid_anchor_refuses_with_specific_mapping_error(old, new):
    assert_refused(deepcopy(old), deepcopy(new), "unsupported_date_mapping")


# AC3-N11 (negative): equivalent ISO representations cannot create a reschedule or be mistaken for an unsupported mapping.
def test_zero_singapore_calendar_shift_is_a_specific_noop_refusal():
    assert_refused(
        ["2026-11-20T10:00:00+08:00"], ["2026-11-20T02:00:00Z"], "no_op_date_mapping",
    )
