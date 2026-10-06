"""SupabaseBookingRepository against a fake Data API (no network), plus storage
selection (SCRUM-32). Every test carries its case ID from
docs/testcases/scrum_32_testcases.md."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import _supabase_booking_repository, get_booking_repository
from app.config import get_settings
from app.models import Slot
from app.supabase_booking_repository import SupabaseBookingRepository
from app.supabase_repository import SupabaseRepositoryError

URL = "https://project.supabase.co"
KEY = "sb_secret_test"
BOOKING_ID = "2a192261-5e90-4398-90ff-1a2d0eaaff00"
USER_ID = "11111111-1111-4111-8111-111111111111"
EVENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENUE_ID = "99999999-9999-4999-8999-999999999999"


def _row(**overrides: object) -> dict:
    row = {
        "id": BOOKING_ID,
        "venue_id": VENUE_ID,
        "requested_by": USER_ID,
        "event_request_id": EVENT_ID,
        "event_name": "Annual Gala",
        "expected_attendance": 120,
        "requirements_note": "Stage",
        "start_date": "2030-01-10",
        "end_date": "2030-01-11",
        "slots": ["AM", "PM"],
        "status": "pending",
        "decision_reason": None,
        "suggested_alternative": None,
        "decided_by": None,
        "decided_at": None,
        "created_at": "2026-10-05T01:00:00+00:00",
    }
    row.update(overrides)
    return row


class FakeDataAPI:
    """Records requests and replies with a canned response."""

    def __init__(self, status_code: int = 200, body: object = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status_code = status_code
        self.body = [] if body is None else body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.body)

    def repo(self) -> SupabaseBookingRepository:
        return SupabaseBookingRepository(
            URL, KEY, transport=httpx.MockTransport(self)
        )


def _booking() -> BookingRequest:
    return BookingRequest(
        id=BOOKING_ID,
        venue_id=VENUE_ID,
        requested_by=USER_ID,
        event_request_id=EVENT_ID,
        event_name="Annual Gala",
        expected_attendance=120,
        requirements_note="Stage",
        start_date=date(2030, 1, 10),
        end_date=date(2030, 1, 11),
        slots=[Slot.AM, Slot.PM],
    )


# AC1-X2 (cross-cutting): the row is posted to venue_booking_requests and the stored row returned
def test_create_posts_the_row_and_returns_what_was_stored() -> None:
    api = FakeDataAPI(201, [_row()])

    stored = api.repo().create(_booking())

    request = api.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/rest/v1/venue_booking_requests"
    assert request.headers["apikey"] == KEY
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["Prefer"] == "return=representation"
    sent = json.loads(request.content)
    assert sent["venue_id"] == VENUE_ID
    assert sent["requested_by"] == USER_ID
    assert sent["slots"] == ["AM", "PM"]
    assert sent["status"] == "pending"
    assert sent["start_date"] == "2030-01-10"
    assert sent["decided_by"] is None
    assert stored.id == BOOKING_ID
    assert stored.slots == [Slot.AM, Slot.PM]


# AC3-X3 (cross-cutting): pending rows are requested oldest first
def test_list_by_status_asks_for_the_status_oldest_first() -> None:
    api = FakeDataAPI(200, [_row()])

    result = api.repo().list_by_status(BookingRequestStatus.PENDING)

    params = api.requests[0].url.params
    assert api.requests[0].method == "GET"
    assert params["status"] == "eq.pending"
    assert params["order"] == "created_at.asc,id.asc"
    assert [item.id for item in result] == [BOOKING_ID]


# AC5-X3 (cross-cutting): a requester's rows are requested newest first
def test_list_for_requester_asks_for_their_rows_newest_first() -> None:
    api = FakeDataAPI(200, [_row()])

    result = api.repo().list_for_requester(USER_ID)

    params = api.requests[0].url.params
    assert params["requested_by"] == f"eq.{USER_ID}"
    assert params["order"] == "created_at.desc,id.desc"
    assert len(result) == 1


# AC5-H2 (happy): a single row is requested by id and decoded with its decision fields
def test_get_filters_by_id_and_decodes_a_decided_row() -> None:
    api = FakeDataAPI(
        200,
        [
            _row(
                status="rejected",
                decision_reason="Under maintenance",
                suggested_alternative="Hall B",
                decided_by=USER_ID,
                decided_at="2026-10-06T01:00:00+00:00",
            )
        ],
    )

    booking = api.repo().get(BOOKING_ID)

    assert api.requests[0].url.params["id"] == f"eq.{BOOKING_ID}"
    assert booking is not None
    assert booking.status is BookingRequestStatus.REJECTED
    assert booking.decision_reason == "Under maintenance"
    assert booking.suggested_alternative == "Hall B"


# AC5-N15 (negative): an id with no row returns nothing
def test_get_unknown_id_returns_none() -> None:
    assert FakeDataAPI(200, []).repo().get(BOOKING_ID) is None


# AC5-N18 (negative): a malformed id is treated as absent without calling Supabase
def test_malformed_id_returns_none_without_querying() -> None:
    api = FakeDataAPI()

    assert api.repo().get("not-a-uuid") is None
    assert api.requests == []


# AC6-X8 (cross-cutting): an error reply from the Data API is a repository error
def test_error_status_raises_repository_error() -> None:
    with pytest.raises(SupabaseRepositoryError):
        FakeDataAPI(500, {"message": "boom"}).repo().create(_booking())


# AC6-X8 (cross-cutting): a network failure is a repository error
def test_network_failure_raises_repository_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    repo = SupabaseBookingRepository(URL, KEY, transport=httpx.MockTransport(refuse))

    with pytest.raises(SupabaseRepositoryError):
        repo.list_by_status(BookingRequestStatus.PENDING)


# AC1-X2 (cross-cutting): VENUE_STORAGE_BACKEND=supabase selects the Supabase store
def test_supabase_backend_selects_the_supabase_booking_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VENUE_STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", KEY)
    get_settings.cache_clear()
    _supabase_booking_repository.cache_clear()

    assert isinstance(get_booking_repository(), SupabaseBookingRepository)

    get_settings.cache_clear()
    _supabase_booking_repository.cache_clear()
