"""SCRUM-57 AC1 (hotfix 2, H11): the staff told when an event is cancelled or postponed.

Besides the Organiser and the latest Coordinator (tested with the notices), the AC names:
the Venue Staff member in decided_by of each approved booking, the Technical Support Staff
member in updated_by of each equipment requirement (a requirement still 'requested' has none),
and each Technical Support Staff member assigned through SCRUM-19. Each person once.
"""

from typing import Any

import httpx
import pytest

from app.repositories.event_request_repository import (
    SupabaseEventRequestRepository,
    SupabaseRepositoryError,
)


def repository(tables: dict[str, Any]) -> tuple[SupabaseEventRequestRepository, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        table = request.url.path.rsplit("/", 1)[-1]
        outcome = tables[table]
        if isinstance(outcome, int):
            return httpx.Response(outcome, json={})
        return httpx.Response(200, json=outcome)

    return (
        SupabaseEventRequestRepository(
            "https://example.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler)
        ),
        seen,
    )


FULL = {
    "venue_booking_requests": [{"decided_by": "v1"}, {"decided_by": "v2"}, {"decided_by": "v1"}],
    "equipment_requirements": [{"updated_by": "t1"}, {"updated_by": None}, {"updated_by": "t1"}],
    "technical_support_assignments": [{"staff_id": "t2"}, {"staff_id": "t1"}, {"staff_id": "v2"}],
}


# AC1-H1 (happy): the approvers of the bookings, the staff who last updated each requirement and the
# Technical Support Staff assigned to the event are all told, each once
def test_all_three_groups_of_staff_are_told_once() -> None:
    repo, _ = repository(FULL)

    assert repo.cancellation_staff_ids("e1") == ["t1", "t2", "v1", "v2"]


# AC1-N1 (negative): a requirement still 'requested' has no updated_by, so nobody is told for it
def test_a_requirement_nobody_has_updated_tells_nobody() -> None:
    repo, _ = repository({**FULL, "equipment_requirements": [{"updated_by": None}], "technical_support_assignments": []})

    assert repo.cancellation_staff_ids("e1") == ["v1", "v2"]


# AC1-X1 (cross-cutting): each lookup is scoped to this event and asks for only the column it needs
def test_each_lookup_is_scoped_to_the_event() -> None:
    repo, seen = repository(FULL)

    repo.cancellation_staff_ids("e1")

    by_table = {request.url.path.rsplit("/", 1)[-1]: request.url.params for request in seen}
    assert set(by_table) == {"venue_booking_requests", "equipment_requirements", "technical_support_assignments"}
    assert by_table["venue_booking_requests"]["select"] == "decided_by"
    assert by_table["venue_booking_requests"]["status"] == "eq.cancelled"
    assert by_table["equipment_requirements"]["select"] == "updated_by"
    assert by_table["equipment_requirements"]["updated_by"] == "not.is.null"
    assert by_table["technical_support_assignments"]["select"] == "staff_id"
    for params in by_table.values():
        assert params["event_request_id"] == "eq.e1"


# AC1-N2 (negative): the reservation releases are no longer the source; who reserved a unit is not who the AC names
def test_the_release_table_is_not_read() -> None:
    repo, seen = repository(FULL)

    repo.cancellation_staff_ids("e1")

    assert all("equipment_reservation_releases" not in str(request.url) for request in seen)


# AC1-N3 (negative): if any lookup fails the whole lookup fails, so the service logs it and still tells the others
@pytest.mark.parametrize("table", ["venue_booking_requests", "equipment_requirements", "technical_support_assignments"])
def test_a_failed_lookup_is_reported(table: str) -> None:
    repo, _ = repository({**FULL, table: 500})

    with pytest.raises(SupabaseRepositoryError):
        repo.cancellation_staff_ids("e1")
