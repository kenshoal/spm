"""Release 1 hotfixes in eventRequestService (4, 5, 8, 9, 14, 15, 16)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.models.event_request import EventDetailsUpdate
from app.models.registration import RegistrationSettingsUpdate
from app.repositories.event_request_repository import (
    EventRequestRpcError,
    SupabaseEventRequestRepository,
    SupabaseRepositoryError,
)
from app.repositories.registration_repository import (
    RegistrationRpcError,
    SupabaseRegistrationRepository,
)
from app.services.event_request_service import (
    EventDetailsConflictError,
    EventRequestForbiddenError,
    EventRequestService,
)
from app.services.registration_service import (
    CapacityBelowTakenError,
    EventNotVisibleError,
    RegistrationService,
    RegistrationSettingsInvalidError,
    RegistrationSettingsNotAllowedError,
)

NOW = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=3)


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        return lambda **kwargs: self.calls.append((name, kwargs))


def event_row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "e1",
        "organiser_id": "o1",
        "status": "Confirmed",
        "event_name": "Gala",
        "proposed_date_times": ["2030-02-01T02:00:00+00:00"],
        "updated_at": "2030-01-01T00:00:00+00:00",
        **overrides,
    }


def settings_refusal(error: RegistrationRpcError) -> RegistrationService:
    def refuse(*args: Any) -> None:
        raise error

    return RegistrationService(SimpleNamespace(set_registration_settings=refuse))


# AC4-H1 (happy): the coordinator's settings reach the database function unchanged
def test_settings_are_sent_to_the_database_function() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "e1"})

    repository = SupabaseRegistrationRepository(
        "https://example.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler)
    )

    repository.set_registration_settings("e1", "c1", NOW, LATER, 50, NOW)

    assert seen[0].url.path.endswith("/rpc/set_event_registration_settings")
    assert b'"p_capacity":50' in seen[0].content.replace(b" ", b"")


# AC4-N1, AC4-N2, AC4-N3, AC4-N4 (negative): each database refusal becomes its own error
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RegistrationRpcError("x", errcode="P0002"), EventNotVisibleError),
        (RegistrationRpcError("x", errcode="P0003"), EventNotVisibleError),
        (RegistrationRpcError("x", errcode="22023"), RegistrationSettingsInvalidError),
        (
            RegistrationRpcError("x", errcode="P0004", reason="capacity below places taken"),
            CapacityBelowTakenError,
        ),
        (RegistrationRpcError("x", errcode="P0004", reason="other"),
         RegistrationSettingsNotAllowedError),
    ],
    ids=["AC4-N1", "AC4-N2", "AC4-N3", "AC4-N4", "AC4-N5"],
)
def test_settings_refusals_map_to_specific_errors(
    error: RegistrationRpcError, expected: type[Exception]
) -> None:
    with pytest.raises(expected):
        settings_refusal(error).set_registration_settings("e1", "c1", NOW, LATER, 5, NOW)


# AC4-B1 (boundary): closing exactly when it opens is refused, one second later is accepted
def test_settings_must_close_after_opening() -> None:
    with pytest.raises(ValidationError):
        RegistrationSettingsUpdate(
            registration_opens_at=NOW, registration_closes_at=NOW, registration_capacity=1
        )
    RegistrationSettingsUpdate(
        registration_opens_at=NOW,
        registration_closes_at=NOW + timedelta(seconds=1),
        registration_capacity=1,
    )


# AC4-B2 (boundary): capacity 0 is refused and 1 is accepted
def test_settings_capacity_boundary() -> None:
    with pytest.raises(ValidationError):
        RegistrationSettingsUpdate(
            registration_opens_at=NOW, registration_closes_at=LATER, registration_capacity=0
        )


# AC5-H1 (happy): attendees see where the event is
def test_public_events_include_their_venues() -> None:
    event = {
        "id": "e1",
        "status": "Confirmed",
        "event_name": "Gala",
        "purpose": "p",
        "description": "d",
        "proposed_date_times": [],
        "registration_opens_at": None,
        "registration_closes_at": None,
        "registration_capacity": 5,
    }
    venue = {"name": "Hall A", "location": "Marina"}
    service = RegistrationService(
        SimpleNamespace(
            get_event=lambda event_id: event,
            places_taken=lambda event_id: 1,
            list_event_venues=lambda ids: {"e1": [venue]},
        )
    )

    assert service.get_event("e1")["venues"] == [venue]


# AC5-N1 (negative): a failed venue lookup does not hide the event
def test_public_event_survives_a_venue_lookup_failure() -> None:
    def fail(ids: list[str]) -> None:
        raise SupabaseRepositoryError("down")

    event = {
        "id": "e1",
        "status": "Confirmed",
        "event_name": "Gala",
        "purpose": "p",
        "description": "d",
        "proposed_date_times": [],
        "registration_opens_at": None,
        "registration_closes_at": None,
        "registration_capacity": 5,
    }
    service = RegistrationService(
        SimpleNamespace(
            get_event=lambda event_id: event,
            places_taken=lambda event_id: 1,
            list_event_venues=fail,
        )
    )

    assert service.get_event("e1")["venues"] == []


def coordinator_service(
    before: dict[str, Any], after: dict[str, Any], **extra: Any
) -> tuple[EventRequestService, Spy]:
    reads = iter([before, after])
    repository = SimpleNamespace(
        get_by_id=lambda event_id: next(reads, after),
        update_by_coordinator=lambda *args: after,
        list_registered_attendee_ids=lambda event_id: ["a1"],
        **extra,
    )
    spy = Spy()
    service = EventRequestService(repository, spy)
    service._row_to_response = lambda row: row  # type: ignore[method-assign]
    return service, spy


UPDATE = {"expected_updated_at": NOW.isoformat()}


# AC8-H1 (happy): an ordinary edit on a Planning event tells nobody
def test_ordinary_edit_sends_nothing() -> None:
    service, spy = coordinator_service(
        event_row(status="Planning"), event_row(status="Planning", purpose="new")
    )

    service.update_by_coordinator("e1", "c1", EventDetailsUpdate(**UPDATE, purpose="new"))

    assert spy.calls == []


# AC8-H2, AC9-H2 (happy): an edit that reopens a Confirmed event tells the Organiser
def test_edit_that_reopens_a_confirmed_event_tells_the_organiser() -> None:
    service, spy = coordinator_service(
        event_row(), event_row(status="Planning", expected_attendance=500)
    )

    service.update_by_coordinator(
        "e1", "c1", EventDetailsUpdate(**UPDATE, expected_attendance=500)
    )

    assert [name for name, _ in spy.calls] == ["notify_event_no_longer_confirmed"]
    assert spy.calls[0][1]["organiser_id"] == "o1"


# AC8-H3 (happy): moving the date tells registered attendees
def test_date_edit_tells_registered_attendees() -> None:
    new_date = "2030-03-01T02:00:00+00:00"
    service, spy = coordinator_service(
        event_row(status="Planning"),
        event_row(status="Planning", proposed_date_times=[new_date]),
    )

    service.update_by_coordinator(
        "e1", "c1", EventDetailsUpdate(**UPDATE, proposed_date_times=[new_date])
    )

    assert [name for name, _ in spy.calls] == ["notify_event_changed"]
    assert spy.calls[0][1]["attendee_ids"] == ["a1"]


# AC9-N1 (negative): an event that stays Confirmed sends no "no longer confirmed" notice
def test_event_staying_confirmed_sends_no_notice() -> None:
    service, spy = coordinator_service(event_row(), event_row(purpose="new"))

    service.update_by_coordinator("e1", "c1", EventDetailsUpdate(**UPDATE, purpose="new"))

    assert spy.calls == []


# AC8-N1, AC8-N2 (negative): an unassigned or stale edit becomes its specific error
@pytest.mark.parametrize(
    ("errcode", "expected"),
    [("P0003", EventRequestForbiddenError), ("P0004", EventDetailsConflictError)],
    ids=["AC8-N1", "AC8-N2"],
)
def test_edit_refusals_map_to_specific_errors(errcode: str, expected: type[Exception]) -> None:
    def refuse(*args: Any) -> None:
        raise EventRequestRpcError("x", errcode=errcode)

    service = EventRequestService(
        SimpleNamespace(get_by_id=lambda event_id: event_row(), update_by_coordinator=refuse), Spy()
    )

    with pytest.raises(expected):
        service.update_by_coordinator("e1", "c1", EventDetailsUpdate(**UPDATE, purpose="x"))


# AC8-N3 (negative): an edit with nothing to change, or clearing a value, is refused
@pytest.mark.parametrize(
    "fields",
    [{}, {"purpose": None}, {"purpose": "  "}],
    ids=["nothing", "cleared", "blank"],
)
def test_empty_edits_are_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EventDetailsUpdate(**UPDATE, **fields)


def event_repository(rows: dict[str, list[dict[str, Any]]]) -> SupabaseEventRequestRepository:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows[request.url.path.rsplit("/", 1)[-1]])

    return SupabaseEventRequestRepository(
        "https://example.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler)
    )


# AC14-H1 (happy): arrangements list approved venues and how much equipment is reserved
def test_arrangements_add_up_reservations_per_requirement() -> None:
    repository = event_repository(
        {
            "venue_booking_requests": [
                {
                    "start_date": "2030-02-01",
                    "end_date": "2030-02-01",
                    "start_minute": 600,
                    "end_minute": 720,
                    "venues": {"name": "Hall A", "location": "Marina"},
                }
            ],
            "equipment_requirements": [
                {"id": "r1", "equipment_type": "Projector", "quantity": 3},
                {"id": "r2", "equipment_type": "Mic", "quantity": 1},
            ],
            "equipment_reservations": [
                {"requirement_id": "r1", "quantity": 2},
                {"requirement_id": "r1", "quantity": 1},
            ],
        }
    )

    result = repository.get_event_arrangements("e1")

    assert result["venues"][0]["name"] == "Hall A"
    assert result["equipment"] == [
        {"equipment_type": "Projector", "quantity": 3, "reserved": 3},
        {"equipment_type": "Mic", "quantity": 1, "reserved": 0},
    ]


# AC15-H1 (happy): staff are the approvers of bookings and makers of reservations, once each
def test_cancellation_staff_are_unique() -> None:
    repository = event_repository(
        {
            "venue_booking_requests": [{"decided_by": "v1"}, {"decided_by": "v1"}],
            "equipment_reservation_releases": [{"created_by": "t1"}],
        }
    )

    assert repository.cancellation_staff_ids("e1") == ["t1", "v1"]


def cancelled_event() -> Any:
    return SimpleNamespace(id="e1", organiser_id="o1", event_name="Gala")


# AC15-H2 (happy): the cancellation notice reaches organiser, coordinator and staff, once each
def test_cancellation_notice_includes_staff() -> None:
    spy = Spy()
    service = EventRequestService(
        SimpleNamespace(
            cancellation_staff_ids=lambda event_id: ["o1", "v1", "t1"],
            latest_coordinator_id=lambda event_id: "c1",
        ),
        spy,
    )

    service.notify_owners_of_cancellation(cancelled_event())

    assert spy.calls[0][1]["recipient_ids"] == ["o1", "v1", "t1", "c1"]


# AC15-N1 (negative): a failed staff lookup still tells the organiser and coordinator
def test_cancellation_notice_survives_a_staff_lookup_failure() -> None:
    def fail(event_id: str) -> None:
        raise SupabaseRepositoryError("down")

    spy = Spy()
    service = EventRequestService(
        SimpleNamespace(
            cancellation_staff_ids=fail, latest_coordinator_id=lambda event_id: "c1"
        ),
        spy,
    )

    service.notify_owners_of_cancellation(cancelled_event())

    assert spy.calls[0][1]["recipient_ids"] == ["o1", "c1"]


# AC16-H1 (happy): each registration in the list carries its attendee's email
def test_registration_info_adds_attendee_emails() -> None:
    service = RegistrationService(
        SimpleNamespace(
            get_event_access=lambda event_id: {
                "id": "e1",
                "organiser_id": "o1",
                "registration_capacity": 5,
            },
            list_for_event=lambda event_id: [{"id": "r1", "status": "Registered"}],
            places_taken=lambda event_id: 1,
            attendee_emails=lambda event_id: {"r1": "a@example.com"},
            event_venue_capacity=lambda event_id: None,
        )
    )

    info = service.registration_info("e1", "o1", ("event_organiser",))

    assert info["registrations"][0]["attendee_email"] == "a@example.com"


# AC16-N1 (negative): a failed email lookup still returns the list, without emails
def test_registration_info_survives_an_email_lookup_failure() -> None:
    def fail(event_id: str) -> None:
        raise SupabaseRepositoryError("down")

    service = RegistrationService(
        SimpleNamespace(
            get_event_access=lambda event_id: {
                "id": "e1",
                "organiser_id": "o1",
                "registration_capacity": 5,
            },
            list_for_event=lambda event_id: [{"id": "r1", "status": "Registered"}],
            places_taken=lambda event_id: 1,
            attendee_emails=fail,
            event_venue_capacity=lambda event_id: None,
        )
    )

    info = service.registration_info("e1", "o1", ("event_organiser",))

    assert info["registrations"][0]["attendee_email"] is None
