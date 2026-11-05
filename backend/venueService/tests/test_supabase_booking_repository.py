"""SupabaseBookingRepository against a fake Data API (no network), plus storage
selection (SCRUM-32). Every test carries its case ID from
docs/testcases/scrum_32_testcases.md."""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import pytest

from app.booking_models import BookingRequest, BookingRequestStatus
from app.booking_repository import (
    BookingEventChangedError,
    BookingEventNotFoundError,
    BookingNotCancellableError,
    BookingReplacementRefusedError,
    BookingRequestNotFoundError,
    _supabase_booking_repository,
    get_booking_repository,
)
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
EVENT_VERSION = datetime.fromisoformat("2026-10-22T00:00:00+00:00")


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


# AC1-X2, AC3-X13 (cross-cutting): the complete prepared booking and verified version use the atomic creation RPC without changing the returned booking contract.
def test_create_posts_the_row_and_returns_what_was_stored() -> None:
    api = FakeDataAPI(200, _row())
    booking = _booking()

    stored = api.repo().create(booking, expected_event_updated_at=EVENT_VERSION)

    assert len(api.requests) == 1
    request = api.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/rest/v1/rpc/create_event_venue_booking_request"
    assert request.headers["apikey"] == KEY
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["Accept"] == "application/vnd.pgrst.object+json"
    sent = json.loads(request.content)
    assert sent == {
        "p_booking": booking.model_dump(mode="json"),
        "p_expected_event_updated_at": EVENT_VERSION.isoformat(),
    }
    assert sent["p_booking"]["venue_id"] == VENUE_ID
    assert sent["p_booking"]["requested_by"] == USER_ID
    assert sent["p_booking"]["slots"] == ["AM", "PM"]
    assert (sent["p_booking"]["start_minute"], sent["p_booking"]["end_minute"]) == (420, 1080)
    assert sent["p_booking"]["status"] == "pending"
    assert sent["p_booking"]["start_date"] == "2030-01-10"
    assert sent["p_booking"]["decided_by"] is None
    assert stored == BookingRequest.model_validate(_row())


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
        FakeDataAPI(500, {"message": "boom"}).repo().create(_booking(), expected_event_updated_at=EVENT_VERSION)


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


# AC3-X2 (cross-cutting): one event's rows are requested oldest first
def test_list_for_event_asks_for_the_events_rows_oldest_first() -> None:
    api = FakeDataAPI(200, [_row()])

    result = api.repo().list_for_event(EVENT_ID)

    params = api.requests[0].url.params
    assert params["event_request_id"] == f"eq.{EVENT_ID}"
    assert params["order"] == "created_at.asc,id.asc"
    assert [item.id for item in result] == [BOOKING_ID]


# AC3-X2 (cross-cutting): a malformed event id is answered without calling Supabase
def test_list_for_event_with_a_malformed_id_returns_nothing_without_querying() -> None:
    api = FakeDataAPI()

    assert api.repo().list_for_event("not-a-uuid") == []
    assert api.requests == []


CANCEL_PATH = "/rest/v1/rpc/cancel_venue_booking_request"


# AC4-X4 (cross-cutting): cancel calls the database function and returns the updated row
def test_cancel_calls_the_function_and_returns_the_cancelled_row() -> None:
    api = FakeDataAPI(
        200,
        _row(status="cancelled", cancelled_by=USER_ID, cancelled_at="2026-10-18T01:00:00+00:00"),
    )

    booking = api.repo().cancel(BOOKING_ID, USER_ID)

    request = api.requests[0]
    assert request.method == "POST"
    assert request.url.path == CANCEL_PATH
    assert json.loads(request.content) == {
        "p_booking_request_id": BOOKING_ID,
        "p_cancelled_by": USER_ID,
    }
    assert booking.status is BookingRequestStatus.CANCELLED
    assert booking.cancelled_by == USER_ID


# AC4-X4 (cross-cutting): the function's error codes map to the store's errors
@pytest.mark.parametrize(
    ("status_code", "code", "expected"),
    [
        (404, "P0002", BookingRequestNotFoundError),
        (409, "55000", BookingNotCancellableError),
        (500, "XX000", SupabaseRepositoryError),
    ],
    ids=["not-found", "not-cancellable", "failure"],
)
def test_cancel_maps_function_errors(status_code: int, code: str, expected: type) -> None:
    api = FakeDataAPI(status_code, {"code": code, "message": "x"})

    with pytest.raises(expected):
        api.repo().cancel(BOOKING_ID, USER_ID)


# AC4-N5 (negative): a malformed id is not found without calling Supabase
def test_cancel_with_a_malformed_id_does_not_query() -> None:
    api = FakeDataAPI()

    with pytest.raises(BookingRequestNotFoundError):
        api.repo().cancel("not-a-uuid", USER_ID)
    assert api.requests == []


# AC4-N7 (negative): a network failure is a repository error
def test_cancel_network_failure_raises_repository_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    repo = SupabaseBookingRepository(URL, KEY, transport=httpx.MockTransport(refuse))

    with pytest.raises(SupabaseRepositoryError):
        repo.cancel(BOOKING_ID, USER_ID)


# AC1-X2 (cross-cutting): complete Pending creation data carries no fabricated cancellation actor or timestamp.
def test_create_keeps_cancellation_audit_unset() -> None:
    api = FakeDataAPI(200, _row())

    api.repo().create(_booking(), expected_event_updated_at=EVENT_VERSION)

    sent = json.loads(api.requests[0].content)["p_booking"]
    assert sent["cancelled_by"] is None
    assert sent["cancelled_at"] is None


# AC2-X3 (cross-cutting): the Supabase query asks for one venue's approved bookings that touch the window
def test_list_approved_for_venue_filters_in_the_query() -> None:
    api = FakeDataAPI(200, [_row(status="approved", decided_by=USER_ID, decided_at="2026-10-06T01:00:00+00:00")])

    result = api.repo().list_approved_for_venue(VENUE_ID, date(2026, 10, 1), date(2026, 10, 31))

    params = api.requests[0].url.params
    assert params["venue_id"] == f"eq.{VENUE_ID}"
    assert params["status"] == "eq.approved"
    assert params["start_date"] == "lte.2026-10-31"
    assert params["end_date"] == "gte.2026-10-01"
    assert [item.id for item in result] == [BOOKING_ID]


# AC2-X3 (cross-cutting): a malformed venue id is answered without calling Supabase
def test_list_approved_for_venue_with_a_malformed_id_returns_nothing_without_querying() -> None:
    api = FakeDataAPI()

    assert api.repo().list_approved_for_venue("not-a-uuid", date(2026, 10, 1), date(2026, 10, 31)) == []
    assert api.requests == []


REPLACE_PATH = "/rest/v1/rpc/create_replacement_venue_booking_request"
OLD_ID = "5b5b5b5b-5b5b-45b5-85b5-5b5b5b5b5b5b"


# AC4-H1 (happy): a replacement goes through the database function with only the new id, venue and requester
def test_create_replacement_calls_the_function_and_returns_the_linked_row() -> None:
    api = FakeDataAPI(200, _row(replaces_booking_id=OLD_ID))

    booking = api.repo().create_replacement(OLD_ID, _booking(), expected_event_updated_at=EVENT_VERSION)

    request = api.requests[0]
    assert request.method == "POST"
    assert request.url.path == REPLACE_PATH
    assert json.loads(request.content) == {
        "p_replaces_booking_id": OLD_ID,
        "p_new_id": BOOKING_ID,
        "p_venue_id": VENUE_ID,
        "p_requested_by": USER_ID,
        "p_expected_event_updated_at": EVENT_VERSION.isoformat(),
    }
    assert booking.replaces_booking_id == OLD_ID


# AC4-N1, AC4-N2, AC4-N3, AC4-N4, AC4-N5, AC4-N6, AC4-N7 (negative): the function's errors map to the store's errors
@pytest.mark.parametrize(
    ("status_code", "code", "message", "expected"),
    [
        (409, "P0004", "booking is not approved", ("refused", "not_approved")),
        (409, "P0004", "booking is not flagged as needing a new venue", ("refused", "not_flagged")),
        (422, "22023", "a replacement must be at a different venue", ("refused", "same_venue")),
        (409, "23505", "duplicate key value", ("refused", "replacement_exists")),
        (409, "P0004", "Event request changed; refresh before booking", BookingEventChangedError),
        (404, "P0003", "Caller is not the assigned coordinator", BookingEventNotFoundError),
        (404, "P0002", "Venue not found", BookingEventNotFoundError),
        (404, "P0002", "booking request not found", BookingRequestNotFoundError),
        (500, "XX000", "boom", SupabaseRepositoryError),
    ],
    ids=["AC4-N2", "AC4-N1", "AC4-N3", "AC4-N5", "AC4-N6", "AC4-N7", "AC4-N4", "AC4-N9", "failure"],
)
def test_create_replacement_maps_function_errors(status_code: int, code: str, message: str, expected: object) -> None:
    api = FakeDataAPI(status_code, {"code": code, "message": message})

    if isinstance(expected, tuple):
        with pytest.raises(BookingReplacementRefusedError) as raised:
            api.repo().create_replacement(OLD_ID, _booking(), expected_event_updated_at=EVENT_VERSION)
        assert raised.value.reason == expected[1]
    else:
        with pytest.raises(expected):
            api.repo().create_replacement(OLD_ID, _booking(), expected_event_updated_at=EVENT_VERSION)


# AC4-N9 (negative): a malformed booking id is not found without calling Supabase
def test_create_replacement_with_a_malformed_id_does_not_query() -> None:
    api = FakeDataAPI()

    with pytest.raises(BookingRequestNotFoundError):
        api.repo().create_replacement("not-a-uuid", _booking(), expected_event_updated_at=EVENT_VERSION)
    assert api.requests == []


# AC4-N6 (negative): an event version without a time zone is not sent
def test_create_replacement_needs_a_timezone_aware_event_version() -> None:
    api = FakeDataAPI()

    with pytest.raises(SupabaseRepositoryError):
        api.repo().create_replacement(OLD_ID, _booking(), expected_event_updated_at=datetime.fromisoformat("2026-10-22T00:00:00"))  # naive on purpose
    assert api.requests == []


# AC1-X2 (cross-cutting): the Supabase store has nothing to do for a block's flag, because the database flags in create_venue_block
def test_marking_a_booking_needs_no_request_in_supabase_mode() -> None:
    api = FakeDataAPI()

    api.repo().mark_needs_new_venue(BOOKING_ID)

    assert api.requests == []
