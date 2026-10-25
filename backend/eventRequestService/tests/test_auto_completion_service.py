"""Prepared storage outcomes prove sweep mechanics; native SQL proves eligibility and writes."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.repositories import SupabaseRepositoryError
from app.services.auto_completion import AutoCompletionService

NOW = datetime(2026, 10, 23, 4, tzinfo=UTC)


def uid(number):
    return f"40000000-0000-4000-8000-{number:012d}"


class PreparedRepository:
    """Protocol records, not a simulated completion rule or mutable lifecycle."""

    def __init__(self, pages, outcomes):
        self.pages = deepcopy(pages)
        self.outcomes = outcomes
        self.reads = []
        self.completions = []

    def list_confirmed_for_auto_completion(self, *, after_id, limit):
        self.reads.append((after_id, limit))
        return deepcopy(self.pages[after_id])

    def complete_overdue_event_request(self, event_request_id, as_of):
        self.completions.append((event_request_id, as_of))
        prepared = self.outcomes[event_request_id]
        if isinstance(prepared, Exception):
            raise prepared
        return prepared


def row(number, end="2026-10-16T03:59:59Z"):
    return {"id": uid(number), "final_event_end_at": end}


# AC1-X1 (cross-cutting): one aware sweep clock spans all short pages, missing ends skip safely and one failing event never starves later work.
def test_sweep_uses_one_clock_and_all_pages_with_per_event_isolation():
    pages = {
        None: [row(1), row(2, None)],
        uid(2): [row(3), row(4)],
        uid(4): [row(5)],
        uid(5): [],
    }
    repository = PreparedRepository(
        pages,
        {
            uid(1): True,
            uid(3): SupabaseRepositoryError("prepared outage"),
            uid(4): False,
            uid(5): True,
        },
    )
    clock_calls = []

    def clock():
        clock_calls.append(True)
        return NOW.astimezone(timezone(timedelta(hours=8))) + timedelta(
            hours=len(clock_calls) - 1
        )

    report = AutoCompletionService(repository, clock=clock, page_size=1000).run_once()
    assert report == {
        "examined": 5,
        "completed": 2,
        "unchanged": 1,
        "skipped_missing_end": 1,
        "failed": 1,
    }
    assert clock_calls == [True]
    assert repository.reads == [
        (None, 1000),
        (uid(2), 1000),
        (uid(4), 1000),
        (uid(5), 1000),
    ]
    assert repository.completions == [(uid(i), NOW) for i in (1, 3, 4, 5)]
    assert all(value.tzinfo == UTC for _, value in repository.completions)
    assert repository.pages == pages


# AC1-H2 (happy): an explicit aware manual-pass clock bypasses the clock provider and an empty sweep performs no mutations.
def test_explicit_clock_and_empty_sweep_do_not_call_completion():
    repository = PreparedRepository({None: []}, {})

    def forbidden_clock():
        raise AssertionError("explicit as_of must not read another clock")

    assert AutoCompletionService(repository, clock=forbidden_clock).run_once(
        as_of=NOW
    ) == {
        "examined": 0,
        "completed": 0,
        "unchanged": 0,
        "skipped_missing_end": 0,
        "failed": 0,
    }
    assert repository.reads == [(None, 1000)]
    assert repository.completions == []


@pytest.mark.parametrize(
    "explicit", [True, False], ids=["explicit-naive", "provider-naive"]
)
# AC1-N2 (negative): a timezone-free eligibility clock is rejected before any storage read or mutation.
def test_naive_clock_is_refused_before_storage(explicit):
    repository = PreparedRepository({None: []}, {})
    naive = NOW.replace(tzinfo=None)
    service = AutoCompletionService(repository, clock=lambda: naive)
    with pytest.raises(ValueError):
        service.run_once(as_of=naive if explicit else None)
    assert repository.reads == []
    assert repository.completions == []
