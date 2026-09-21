from datetime import date

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.availability_models import EventAllocation
from app.block_models import BlockStatus
from app.block_repository import block_repository
from app.event_allocations import HttpEventAllocationSource, get_event_allocations
from app.main import app
from app.routers.block_checks import current_venue_date

client = TestClient(app)


@pytest.fixture
def venue():
    result = client.post(
        "/venues", json={"name": "Hall", "location": "Campus", "max_capacity": 50}
    )
    assert result.status_code == 201
    return result.json()["id"]


def make_block(venue, **overrides):
    response = client.post(
        f"/venues/{venue}/blocks",
        json={
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "slots": ["AM"],
            "reason_category": "maintenance",
        }
        | overrides,
    )
    assert response.status_code == 201
    return response.json()["id"]


def check(venue, **overrides):
    return client.post(
        f"/venues/{venue}/availability",
        json={
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "slots": ["AM"],
        }
        | overrides,
    )


def allocation(venue, **overrides):
    return EventAllocation.model_validate(
        {
            "allocation_id": "allocation-1",
            "venue_id": venue,
            "event_request_id": "event-1",
            "event_name": "Confirmed event",
            "event_status": "Confirmed",
            "coordinator_id": "coordinator-1",
            "allocation_status": "active",
            "start_date": "2026-10-01",
            "end_date": "2026-10-04",
            "slots": ["AM", "PM"],
        }
        | overrides
    )


def configure_source(rows):
    class Source:
        def list_for_period(self, venue_id, start_date, end_date):
            assert start_date == date(2026, 10, 2)
            assert end_date == date(2026, 10, 3)
            return rows

    app.dependency_overrides[get_event_allocations] = lambda: Source()
    app.dependency_overrides[current_venue_date] = lambda: date(2026, 10, 2)


def test_availability_flow_reports_conflicts_without_writes(venue):
    assert check(venue).json()["available"] is True
    block = make_block(venue)
    result = check(
        venue, start_date="2026-09-30", end_date="2026-10-02", slots=["AM", "PM"]
    )
    assert result.status_code == 200
    assert result.json() == {
        "venue_id": venue,
        "available": False,
        "reasons": ["active_block"],
        "unsupported_slots": [],
        "conflicts": [
            {
                "block_id": block,
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "slots": ["AM"],
            }
        ],
    }
    assert len(block_repository.list()) == 1
    assert check(venue, slots=["PM"]).json()["available"] is True
    block_repository.get(block).status = BlockStatus.LIFTED
    assert check(venue).json()["available"] is True


@pytest.mark.parametrize(
    "day,available",
    [
        ("2026-09-30", True),
        ("2026-10-01", False),
        ("2026-10-03", False),
        ("2026-10-04", True),
    ],
)
def test_availability_inclusive_boundaries(venue, day, available):
    make_block(venue)
    assert check(venue, start_date=day, end_date=day).json()["available"] is available


def test_availability_whole_venue_status_and_operating_slots(venue):
    client.patch(
        f"/venues/{venue}", json={"status": "blocked", "operating_slots": ["PM"]}
    )
    response = check(venue).json()
    assert response["available"] is False
    assert response["reasons"] == ["venue_unavailable", "outside_operating_slots"]
    assert response["unsupported_slots"] == ["AM"]


@pytest.mark.parametrize(
    "changes",
    [
        {"slots": []},
        {"slots": ["AM", "AM"]},
        {"slots": [None]},
        {"end_date": "2026-09-30"},
        {"slots": ["invalid"]},
        {"created_by": "spoofed"},
    ],
)
def test_invalid_availability_request(venue, changes):
    assert check(venue, **changes).status_code == 422


def test_missing_venue_availability():
    assert check("missing").status_code == 404


def test_affected_lookup_filters_and_groups_actual_allocations(venue):
    block = make_block(venue)
    first = allocation(venue)
    configure_source(
        [
            first,
            first,  # repeated upstream row must not duplicate affected period
            allocation(venue, allocation_id="second", slots=["AM"]),
            allocation(venue, allocation_id="draft", event_status="Draft"),
            allocation(venue, allocation_id="cancelled", allocation_status="cancelled"),
            allocation(
                venue,
                allocation_id="past",
                start_date="2026-09-01",
                end_date="2026-10-01",
            ),
            allocation(venue, allocation_id="different-slot", slots=["NIGHT"]),
            allocation("another-venue", allocation_id="other"),
            allocation(
                venue,
                allocation_id="later",
                start_date="2026-10-04",
                end_date="2026-10-05",
            ),
        ]
    )
    response = client.get(f"/venues/{venue}/blocks/{block}/affected-events")
    assert response.status_code == 200
    assert response.json() == [
        {
            "event_request_id": "event-1",
            "event_name": "Confirmed event",
            "coordinator_id": "coordinator-1",
            "affected_periods": [
                {
                    "allocation_id": aid,
                    "start_date": "2026-10-02",
                    "end_date": "2026-10-03",
                    "slots": ["AM"],
                }
                for aid in ["allocation-1", "second"]
            ],
        }
    ]


def test_missing_coordinator_is_reported_not_replaced_with_creator(venue):
    block = make_block(venue)
    configure_source([allocation(venue, coordinator_id=None)])
    assert (
        client.get(f"/venues/{venue}/blocks/{block}/affected-events").json()[0][
            "coordinator_id"
        ]
        is None
    )


def test_unconfigured_source_is_explicit_and_missing_blocks_still_404(venue):
    block = make_block(venue)
    app.dependency_overrides[current_venue_date] = lambda: date(2026, 10, 2)
    assert (
        client.get(f"/venues/{venue}/blocks/{block}/affected-events").status_code == 503
    )
    assert (
        client.get(f"/venues/{venue}/blocks/missing/affected-events").status_code == 404
    )
    assert (
        client.get(f"/venues/wrong/blocks/{block}/affected-events").status_code == 404
    )
    block_repository.get(block).status = BlockStatus.LIFTED
    assert client.get(f"/venues/{venue}/blocks/{block}/affected-events").json() == []


def test_inconsistent_coordinators_fail_instead_of_selecting_wrong_recipient(venue):
    block = make_block(venue)
    configure_source(
        [
            allocation(venue),
            allocation(venue, allocation_id="second", coordinator_id="different"),
        ]
    )
    assert (
        client.get(f"/venues/{venue}/blocks/{block}/affected-events").status_code == 502
    )


def test_http_source_pagination_and_server_credentials():
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer private-token"
        assert request.url.params["venue_id"] == "venue-1"
        assert request.url.params["start_date"] == "2026-10-01"
        if "cursor" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "allocations": [allocation("venue-1").model_dump(mode="json")],
                    "next_cursor": "page-2",
                },
            )
        assert request.url.params["cursor"] == "page-2"
        return httpx.Response(200, json={"allocations": [], "next_cursor": None})

    source = HttpEventAllocationSource(
        "https://events.example/allocations",
        "private-token",
        httpx.MockTransport(handle),
    )
    assert (
        len(source.list_for_period("venue-1", date(2026, 10, 1), date(2026, 10, 3)))
        == 1
    )
    assert len(calls) == 2


@pytest.mark.parametrize("failure", ["timeout", "http", "invalid", "cursor"])
def test_http_source_failure_never_becomes_empty_success(failure):
    def handle(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("secret-token", request=request)
        if failure == "http":
            return httpx.Response(500, text="private-response")
        if failure == "invalid":
            return httpx.Response(
                200, json={"allocations": [{"proposed_date_times": []}]}
            )
        return httpx.Response(200, json={"allocations": [], "next_cursor": "same"})

    source = HttpEventAllocationSource(
        "https://events.example/allocations", transport=httpx.MockTransport(handle)
    )
    with pytest.raises(HTTPException) as exc:
        source.list_for_period("venue-1", date(2026, 10, 1), date(2026, 10, 3))
    assert exc.value.status_code == 502
    assert exc.value.detail == "Event allocation lookup failed"
