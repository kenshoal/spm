"""AC4/5 completeness at the real adapter/public API boundary; capped HTTP is a double."""

from copy import deepcopy
from datetime import datetime

import httpx
import pytest
from test_arrangement_review_actions import TECH_STAFF, VENUE_STAFF
from test_arrangement_reviews import fixture, normalized, review
from test_organisation_access import client_for

from app.repositories import SupabaseEventRequestRepository

CAP = 3


class CappedPostgrest:
    """Emulate only PostgREST filters, ordering and ranges, including an unknown cap."""

    def __init__(self, arrangement, count, *, fail_later=False, clear_earlier=False):
        other = "equipment_reservation" if arrangement == "venue_booking" else "venue_booking"
        # Expected evidence is specified independently: newest instant, then UUID descending.
        self.expected = [review(n, arrangement=arrangement) for n in range(count, 0, -1)]
        self.expected[-1]["raised_at"] = "2026-10-14T00:00:00Z"
        self.rows = [
            *[review(100 + n, arrangement=arrangement, raised_at="2026-10-16T00:00:00Z",
                     cleared_at="2026-10-16T01:00:00Z", cleared_by=VENUE_STAFF) for n in range(4)],
            *[review(200 + n, arrangement=other, raised_at="2026-10-16T00:00:00Z") for n in range(4)],
            *reversed(deepcopy(self.expected)),
        ]
        self.initial = deepcopy(self.rows)
        self.calls = []
        self.fail_later = fail_later
        self.clear_earlier = clear_earlier
        self.previous_ids = []

    def __call__(self, request):
        self.calls.append(request)
        assert request.method == "GET", "Read-only queue must never mutate storage"
        assert request.url.path == "/rest/v1/arrangement_reviews"
        if len(self.calls) > 1 and self.fail_later:
            return httpx.Response(503, json={"message": "private page-two storage failure"})
        if len(self.calls) == 2 and self.clear_earlier:
            for row in self.rows:
                if row["id"] in self.previous_ids:
                    row["cleared_at"] = "2026-10-17T00:00:00Z"
                    row["cleared_by"] = VENUE_STAFF
        params = request.url.params
        rows = deepcopy(self.rows)
        for field in ("arrangement", "cleared_at"):
            value = params.get(field)
            if value == "is.null":
                rows = [row for row in rows if row[field] is None]
            elif value and value.startswith("eq."):
                rows = [row for row in rows if row[field] == value[3:]]
        # A supported keyset disjunction is ordinary PostgREST transport syntax.
        cursor = params.get("or")
        if cursor:
            import re

            match = re.fullmatch(r"\(raised_at\.lt\.(.+),and\(raised_at\.eq\.(.+),id\.lt\.([^,)]+)\)\)", cursor)
            assert match and match[1] == match[2], "Unexpected cursor transport shape"
            instant = datetime.fromisoformat(match[1])
            rows = [row for row in rows if (datetime.fromisoformat(row["raised_at"]), row["id"]) < (instant, match[3])]
        order = params.get("order", "")
        for term in reversed(order.split(",") if order else []):
            field, direction, *_ = term.split(".")
            rows.sort(key=lambda row: datetime.fromisoformat(row[field]) if field == "raised_at" else row[field], reverse=direction == "desc")
        offset = int(params.get("offset", 0))
        requested = int(params.get("limit", CAP))
        if "range" in request.headers:
            start, end = request.headers["range"].split("-")
            offset = int(start)
            requested = int(end) - offset + 1
        page = rows[offset:offset + min(CAP, requested)]
        self.previous_ids.extend(row["id"] for row in page)
        total = str(len(rows)) if "count=exact" in request.headers.get("prefer", "") else "*"
        span = f"{offset}-{offset + len(page) - 1}" if page else "*"
        return httpx.Response(200, json=page, headers={"Content-Range": f"{span}/{total}", "Range-Unit": "items"})


def read_queue(server, arrangement):
    _, assignments = fixture()
    actor, role = (VENUE_STAFF, "venue_staff") if arrangement == "venue_booking" else (TECH_STAFF, "technical_support")
    repository = SupabaseEventRequestRepository("https://project.supabase.co", "sb_secret_test", transport=httpx.MockTransport(server))
    try:
        with client_for(repository, actor, (role,), assignments) as client:
            return client.get("/arrangement-reviews", params={"arrangement": arrangement})
    finally:
        repository.close()


def assert_complete_queue(arrangement, count):
    server = CappedPostgrest(arrangement, count)
    response = read_queue(server, arrangement)
    assert response.status_code == 200, response.text
    assert normalized(response.json()) == normalized(server.expected)
    assert server.rows == server.initial
    assert all(call.url.params.get("arrangement") == f"eq.{arrangement}" for call in server.calls)
    assert all(call.url.params.get("cleared_at") == "is.null" for call in server.calls)
    assert all(call.url.params.get("order") == "raised_at.desc,id.desc" for call in server.calls)



@pytest.mark.parametrize("count", [2, 3, 7], ids=["AC5-B2", "AC5-B3", "AC5-B4"])
# AC5-B2, AC5-B3, AC5-B4 (boundary): cap-adjacent and multi-page venue queues retain all outstanding evidence behind cleared rows.
def test_staff_queue_is_complete_under_unknown_server_cap(count):
    assert_complete_queue("venue_booking", count)


# AC5-P6 (partition): technical staff receive the complete equipment-domain queue under the same server cap.
def test_equipment_queue_is_complete_under_unknown_server_cap():
    assert_complete_queue("equipment_reservation", 7)


# AC5-N6 (negative): later-page outage must not turn incomplete evidence into a successful staff queue.
def test_later_page_failure_returns_safe_outage_instead_of_partial_success():
    server = CappedPostgrest("venue_booking", 7, fail_later=True)
    response = read_queue(server, "venue_booking")
    assert response.status_code == 502
    assert response.json() == {"detail": "Arrangement reviews unavailable"}
    assert len(server.calls) == 2
    assert server.rows == server.initial


# AC5-X14 (cross-cutting): clearing already-read rows between pages cannot make unread outstanding rows disappear through offset drift.
def test_clearing_earlier_page_does_not_skip_unread_reviews():
    server = CappedPostgrest("venue_booking", 7, clear_earlier=True)
    response = read_queue(server, "venue_booking")
    assert response.status_code == 200, response.text
    assert normalized(response.json()) == normalized(server.expected)
    unread = {row["id"] for row in server.rows if row["arrangement"] == "venue_booking" and row["cleared_at"] is None}
    assert unread <= {row["id"] for row in response.json()}
