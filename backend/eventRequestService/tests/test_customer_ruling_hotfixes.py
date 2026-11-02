"""Release 1 hotfixes 20 to 25: customer rulings (Q&A #104, #103, #69/#121, #99, #59/#61, #80/#106)."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from test_event_change_request import eligible_fixture
from test_event_transition_controller import headers, make_assigned_client

from app.models.event_request import (
    EventChangeDecision,
    EventChangeRequestResponse,
    EventChangeRequestStatus,
)
from app.repositories.event_request_repository import (
    EventRequestRpcError,
    SupabaseEventRequestRepository,
    SupabaseRepositoryError,
)
from app.repositories.registration_repository import SupabaseRegistrationRepository
from app.services.event_request_service import (
    EventChangeRequestConflictError,
    EventChangeRequestForbiddenError,
    EventChangeSelectionError,
    EventRequestService,
)
from app.services.event_transition_service import (
    EventTransitionService,
    OrganiserNotFoundError,
    OrganiserOutsideOrganisationError,
    TransitionNotAllowedError,
)
from app.services.registration_service import RegistrationService


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        return lambda **kwargs: self.calls.append((name, kwargs))


CHANGE = {
    "id": "c1",
    "event_request_id": "e1",
    "organiser_id": "o1",
    "status": "Partially Approved",
    "explanation": "more people, new rooms",
    "proposed_changes": {"expected_attendance": 60},
    "base_event_updated_at": "2030-01-01T00:00:00+00:00",
    "coordinator_id": "coord-1",
    "decision_reason": "Only the numbers can change",
    "created_at": "2030-01-01T00:00:00+00:00",
    "decided_at": "2030-01-02T00:00:00+00:00",
    "rejected_changes": {"venue_requirements": {"value": "new", "reason": "No room"}},
}


def partial_service(partial: Any) -> tuple[EventRequestService, Spy]:
    repository = SimpleNamespace(
        get_by_id=lambda event_id: {"status": "Planning"},
        partially_approve_change_request=partial,
        list_registered_attendee_ids=lambda event_id: [],
    )
    spy = Spy()
    return EventRequestService(repository, spy), spy


DECISION = EventChangeDecision(
    decision="Approved",
    accepted_fields=["expected_attendance"],
    rejected_reasons={"venue_requirements": "No room"},
    reason="Only the numbers can change",
)


# AC20-H1 (happy): the accepted fields and each refusal reach the database function unchanged
def test_partial_approval_is_sent_to_the_database_function() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=CHANGE)

    repository = SupabaseEventRequestRepository(
        "https://example.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler)
    )

    repository.partially_approve_change_request(
        "e1", "c1", "coord-1", ["expected_attendance"], {"venue_requirements": "No room"},
        "Only the numbers can change", None,
    )

    assert seen[0].url.path.endswith("/rpc/partially_approve_event_change_request")
    body = seen[0].read().replace(b" ", b"")
    assert b'"p_accepted_fields":["expected_attendance"]' in body
    assert b'"p_rejections":{"venue_requirements":"Noroom"}' in body.replace(b" ", b"")


# AC20-H2 (happy): the Organiser is told what was applied, what was refused and why
def test_partial_approval_tells_the_organiser_both_sides() -> None:
    service, spy = partial_service(lambda *args: deepcopy(CHANGE))

    saved = service.partially_approve_change_request("e1", "c1", "coord-1", DECISION)

    assert saved.status == EventChangeRequestStatus.PARTIALLY_APPROVED
    assert saved.rejected_changes == CHANGE["rejected_changes"]
    notice = [call for name, call in spy.calls if name == "notify_event_change_partly_approved"]
    assert notice == [{
        "event_request_id": "e1",
        "change_request_id": "c1",
        "organiser_id": "o1",
        "accepted_fields": ["expected_attendance"],
        "refused": {"venue_requirements": "No room"},
        "reason": "Only the numbers can change",
    }]


# AC20-N1, AC20-N2, AC20-N3 (negative): each database refusal becomes its own error
@pytest.mark.parametrize(
    ("errcode", "expected"),
    [
        ("22023", EventChangeSelectionError),
        ("P0003", EventChangeRequestForbiddenError),
        ("P0004", EventChangeRequestConflictError),
    ],
    ids=["AC20-N1", "AC20-N2", "AC20-N3"],
)
def test_partial_refusals_map_to_specific_errors(errcode: str, expected: type[Exception]) -> None:
    def refuse(*args: Any) -> None:
        raise EventRequestRpcError("x", errcode=errcode)

    service, spy = partial_service(refuse)

    with pytest.raises(expected):
        service.partially_approve_change_request("e1", "c1", "coord-1", DECISION)
    assert spy.calls == []


# AC20-N4 (negative): a result that is not a stored partial approval is never announced
@pytest.mark.parametrize("status", ["Approved", "Pending"], ids=["AC20-N4a", "AC20-N4b"])
def test_other_outcomes_are_not_announced_as_partial(status: str) -> None:
    service, spy = partial_service(lambda *args: {**deepcopy(CHANGE), "status": status})

    with pytest.raises(SupabaseRepositoryError):
        service.partially_approve_change_request("e1", "c1", "coord-1", DECISION)
    assert spy.calls == []


# AC20-N5 (negative): accepted fields only mean something for an approval, and need a list
@pytest.mark.parametrize(
    "fields",
    [
        {"decision": "Rejected", "accepted_fields": ["expected_attendance"]},
        {"decision": "Approved", "accepted_fields": []},
        {"decision": "Approved", "rejected_reasons": {"venue_requirements": "No"}},
    ],
    ids=["AC20-N5a", "AC20-N5b", "AC20-N5c"],
)
def test_partial_fields_are_validated(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EventChangeDecision(**fields)


# AC20-X1 (cross-cutting): the decision endpoint sends a partial decision to the partial function
def test_decision_endpoint_routes_a_partial_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repository, event = eligible_fixture("Planning")
    created = client.post(
        f"/event-requests/{event}/change-requests", headers=headers("organiser-1"),
        json={"explanation": "More people, new rooms.", "expected_attendance": 60,
              "venue_requirements": "A bigger room"},
    )
    assert created.status_code == 201, created.text
    pending = created.json()
    calls: list[tuple[Any, ...]] = []

    def partial(*args: Any) -> dict[str, Any]:
        calls.append(args)
        return {**pending, "status": "Partially Approved", "coordinator_id": "coord-1",
                "decided_at": "2030-01-02T00:00:00Z",
                "proposed_changes": {"expected_attendance": 60},
                "rejected_changes": {"venue_requirements": {"value": "A bigger room",
                                                              "reason": "None free"}}}

    def whole(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("A partial decision must not use the whole-request approval")

    monkeypatch.setattr(repository, "partially_approve_change_request", partial, raising=False)
    monkeypatch.setattr(repository, "decide_change_request", whole)
    with client:
        response = client.post(
            f"/event-requests/{event}/change-requests/{pending['id']}/decision",
            headers=headers("coord-1"),
            json={"decision": "Approved", "accepted_fields": ["expected_attendance"],
                  "rejected_reasons": {"venue_requirements": "None free"}},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Partially Approved"
    assert calls == [(event, pending["id"], "coord-1", ["expected_attendance"],
                      {"venue_requirements": "None free"}, None, None)]


# AC20-N6 (negative): a different coordinator cannot make a partial decision
def test_partial_decision_needs_the_assigned_coordinator() -> None:
    client, _, event = eligible_fixture("Planning")
    created = client.post(
        f"/event-requests/{event}/change-requests", headers=headers("organiser-1"),
        json={"explanation": "More people, new rooms.", "expected_attendance": 60,
              "venue_requirements": "A bigger room"},
    )
    pending = created.json()
    with client:
        response = client.post(
            f"/event-requests/{event}/change-requests/{pending['id']}/decision",
            headers=headers("coord-other"),
            json={"decision": "Approved", "accepted_fields": ["expected_attendance"],
                  "rejected_reasons": {"venue_requirements": "None free"}},
        )
    assert response.status_code == 403, response.text


# AC20-H3 (happy): a stored partly approved row, with its refused fields, reads back
def test_response_model_accepts_the_stored_row() -> None:
    assert EventChangeRequestResponse.model_validate(CHANGE).rejected_changes is not None


# ---- Hotfix 21: the Coordinator records a withdrawal (Q&A #103) -------------------------


@pytest.mark.parametrize("status", ["Submitted", "Under Review", "Changes Requested"],
                         ids=["AC21-H1", "AC21-H2", "AC21-H3"])
def test_coordinator_withdraws_a_request_under_review(status: str) -> None:
    client, repository, event = make_assigned_client(status=status)
    with client:
        response = client.post(f"/event-requests/{event}/withdrawal", headers=headers("coord-1"))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Withdrawn"
    assert repository.rows[event]["status"] == "Withdrawn"


# AC21-B1 (boundary): one step further on (Approved) a request can no longer be withdrawn
@pytest.mark.parametrize("status", ["Approved", "Planning", "Confirmed", "Draft"],
                         ids=["AC21-B1", "AC21-B2", "AC21-B3", "AC21-B4"])
def test_a_request_past_review_is_not_withdrawn(status: str) -> None:
    client, repository, event = make_assigned_client(status=status)
    with client:
        response = client.post(f"/event-requests/{event}/withdrawal", headers=headers("coord-1"))

    assert response.status_code == 409, response.text
    assert repository.rows[event]["status"] == status


# AC21-N1 (negative): only the assigned Coordinator can withdraw, and nothing changes
def test_withdrawal_needs_the_assigned_coordinator() -> None:
    client, repository, event = make_assigned_client(status="Under Review")
    with client:
        response = client.post(f"/event-requests/{event}/withdrawal", headers=headers("coord-2"))

    assert response.status_code == 403, response.text
    assert repository.rows[event]["status"] == "Under Review"


# AC21-H4 (happy): the Organiser is told the withdrawal was recorded
def test_withdrawal_tells_the_organiser() -> None:
    spy = Spy()
    repository = SimpleNamespace(
        advance_by_coordinator=lambda *args: {**EVENT_ROW, "status": "Withdrawn"},
    )
    service = EventTransitionService(EventRequestService(repository), spy)

    service.withdraw("e1", "coord-1")

    assert spy.calls == [("notify_event_request_withdrawn",
                          {"event_request_id": "e1", "event_name": "Gala", "organiser_id": "o1"})]


# AC21-N2 (negative): a refused withdrawal tells nobody
def test_refused_withdrawal_tells_nobody() -> None:
    def refuse(*args: Any) -> None:
        raise EventRequestRpcError("x", errcode="P0004")

    spy = Spy()
    service = EventTransitionService(
        EventRequestService(SimpleNamespace(advance_by_coordinator=refuse)), spy)

    with pytest.raises(TransitionNotAllowedError):
        service.withdraw("e1", "coord-1")
    assert spy.calls == []


# ---- Hotfix 22: postponement with or without a new date (Q&A #69, #121) -----------------

EVENT_ROW = {
    "id": "e1",
    "organiser_id": "o1",
    "status": "Postponed",
    "event_name": "Gala",
    "purpose": "p",
    "description": "d",
    "proposed_date_times": ["2030-02-01T02:00:00+00:00"],
    "created_at": "2030-01-01T00:00:00+00:00",
    "updated_at": "2030-01-02T00:00:00+00:00",
}


# AC22-H1 (happy): a Confirmed event is postponed with no new date and its reason is kept
def test_coordinator_postpones_a_confirmed_event() -> None:
    client, repository, event = make_assigned_client(status="Confirmed")
    with client:
        response = client.post(
            f"/event-requests/{event}/postponement", headers=headers("coord-1"),
            json={"reason": "The venue is closed that week"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Postponed"
    assert repository.rows[event]["status"] == "Postponed"


# AC22-B1 (boundary): the Approved..Confirmed states can be postponed, Submitted cannot
@pytest.mark.parametrize(
    ("status", "code"),
    [("Submitted", 409), ("Approved", 200), ("Planning", 200), ("Safety Review", 200),
     ("Confirmed", 200), ("Completed", 409), ("Cancelled", 409), ("Postponed", 409)],
    ids=["AC22-B1", "AC22-B2", "AC22-B3", "AC22-B4", "AC22-B5", "AC22-B6", "AC22-B7", "AC22-B8"],
)
def test_postponement_boundary_by_status(status: str, code: int) -> None:
    client, repository, event = make_assigned_client(status=status)
    with client:
        response = client.post(
            f"/event-requests/{event}/postponement", headers=headers("coord-1"),
            json={"reason": "Not ready"},
        )

    assert response.status_code == code, response.text
    if code == 409:
        assert repository.rows[event]["status"] == status


# AC22-N1 (negative): a blank reason is refused and the event is unchanged
@pytest.mark.parametrize("reason", ["", "   "], ids=["AC22-N1a", "AC22-N1b"])
def test_postponement_needs_a_reason(reason: str) -> None:
    client, repository, event = make_assigned_client(status="Confirmed")
    with client:
        response = client.post(
            f"/event-requests/{event}/postponement", headers=headers("coord-1"),
            json={"reason": reason},
        )

    assert response.status_code == 422, response.text
    assert repository.rows[event]["status"] == "Confirmed"


# AC22-N2 (negative): only the assigned Coordinator postpones or resumes
def test_postponement_needs_the_assigned_coordinator() -> None:
    client, repository, event = make_assigned_client(status="Confirmed")
    with client:
        response = client.post(
            f"/event-requests/{event}/postponement", headers=headers("coord-2"),
            json={"reason": "x"},
        )

    assert response.status_code == 403, response.text
    assert repository.rows[event]["status"] == "Confirmed"


# AC22-H2 (happy): a postponed event gets its new date and goes back to Planning
def test_postponed_event_resumes_on_a_new_date() -> None:
    client, repository, event = make_assigned_client(status="Postponed")
    with client:
        response = client.post(
            f"/event-requests/{event}/resumption", headers=headers("coord-1"),
            json={"proposed_date_times": ["2031-03-01T02:00:00+00:00"]},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Planning"
    assert repository.rows[event]["proposed_date_times"] == ["2031-03-01T02:00:00+00:00"]


# AC22-N3 (negative): only a postponed event resumes, and it needs at least one date
@pytest.mark.parametrize(
    ("status", "body", "code"),
    [("Confirmed", {"proposed_date_times": ["2031-03-01T02:00:00+00:00"]}, 409),
     ("Postponed", {"proposed_date_times": []}, 422),
     ("Postponed", {}, 422)],
    ids=["AC22-N3a", "AC22-N3b", "AC22-N3c"],
)
def test_resumption_is_refused(status: str, body: dict[str, Any], code: int) -> None:
    client, repository, event = make_assigned_client(status=status)
    with client:
        response = client.post(
            f"/event-requests/{event}/resumption", headers=headers("coord-1"), json=body)

    assert response.status_code == code, response.text
    assert repository.rows[event]["status"] == status


# AC22-X1 (cross-cutting): a postponed event can still be cancelled
def test_postponed_event_can_be_cancelled() -> None:
    client, repository, event = make_assigned_client(status="Postponed")
    with client:
        response = client.post(f"/event-requests/{event}/cancellation", headers=headers("coord-1"))

    assert response.status_code == 200, response.text
    assert repository.rows[event]["status"] == "Cancelled"


# AC22-H3 (happy): postponing tells the Organiser, each Attendee and the staff once
def test_postponement_notice_reaches_organiser_attendees_and_staff() -> None:
    repository = SimpleNamespace(
        postpone_by_coordinator=lambda *args: dict(EVENT_ROW),
        list_registered_attendee_ids=lambda event_id: ["a1", "o1"],
        cancellation_staff_ids=lambda event_id: ["s1", "a1"],
    )
    spy = Spy()
    service = EventTransitionService(EventRequestService(repository, spy), spy)

    service.postpone("e1", "coord-1", "Venue closed")

    [(name, call)] = spy.calls
    assert name == "notify_event_postponed"
    assert call["recipient_ids"] == ["o1", "a1", "s1"]
    assert call["reason"] == "Venue closed"


# AC22-N4 (negative): a failed staff lookup still tells the Organiser and the Attendees
def test_postponement_notice_survives_a_staff_lookup_failure() -> None:
    def fail(event_id: str) -> list[str]:
        raise SupabaseRepositoryError("down")

    repository = SimpleNamespace(
        postpone_by_coordinator=lambda *args: dict(EVENT_ROW),
        list_registered_attendee_ids=lambda event_id: ["a1"],
        cancellation_staff_ids=fail,
    )
    spy = Spy()
    service = EventTransitionService(EventRequestService(repository, spy), spy)

    service.postpone("e1", "coord-1", "Venue closed")

    assert spy.calls[0][1]["recipient_ids"] == ["o1", "a1"]


# AC22-H4 (happy): resuming tells the Organiser and the Attendees the new date
def test_resumption_notice_carries_the_new_date() -> None:
    repository = SimpleNamespace(
        resume_postponed=lambda *args: {**EVENT_ROW, "status": "Planning"},
        list_registered_attendee_ids=lambda event_id: ["a1"],
    )
    spy = Spy()
    service = EventTransitionService(EventRequestService(repository, spy), spy)

    service.resume("e1", "coord-1", ["2030-02-01T02:00:00+00:00"])

    [(name, call)] = spy.calls
    assert name == "notify_event_resumed"
    assert call["recipient_ids"] == ["o1", "a1"]
    assert call["proposed_date_times"] == ["2030-02-01T02:00:00+00:00"]


# AC22-N5 (negative): the staff lookup that serves a cancellation serves a postponement too, and
# asks about this event only (SCRUM-57 AC1, hotfix 2 H11: it no longer filters by a release reason)
def test_staff_lookup_serves_a_postponement_and_is_scoped_to_the_event() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    repository = SupabaseEventRequestRepository(
        "https://example.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler)
    )

    repository.cancellation_staff_ids("e1")

    assert seen and all(r.url.params["event_request_id"] == "eq.e1" for r in seen)
    assert all("reason" not in r.url.params for r in seen)


# ---- Hotfix 23: a VIP above the registration capacity, up to the venue (Q&A #99) ---------


def venue_repository(rows: list[dict[str, Any]]) -> SupabaseRegistrationRepository:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    return SupabaseRegistrationRepository(
        "https://example.supabase.co", "sb_secret_test", transport=httpx.MockTransport(handler)
    )


# AC23-H1 (happy): two bookings at different venues add up their seats
def test_venue_capacity_adds_each_venue() -> None:
    repository = venue_repository([
        {"venue_id": "v1", "venues": {"max_capacity": 300}},
        {"venue_id": "v2", "venues": {"max_capacity": 40}},
    ])

    assert repository.event_venue_capacity("e1") == 340


# AC23-B1 (boundary): two bookings at the same venue count its seats once
def test_venue_capacity_counts_a_venue_once() -> None:
    repository = venue_repository([
        {"venue_id": "v1", "venues": {"max_capacity": 300}},
        {"venue_id": "v1", "venues": {"max_capacity": 300}},
    ])

    assert repository.event_venue_capacity("e1") == 300


# AC23-N1 (negative): an event with no approved booking has no venue capacity
def test_venue_capacity_is_none_without_a_booking() -> None:
    assert venue_repository([]).event_venue_capacity("e1") is None


# AC23-H2 (happy): the registration list tells the Coordinator the venue capacity
def test_registration_info_carries_the_venue_capacity() -> None:
    event = {"id": "e1", "organiser_id": "o1", "registration_capacity": 5, "status": "Confirmed"}
    service = RegistrationService(SimpleNamespace(
        get_event_access=lambda event_id: event,
        list_for_event=lambda event_id: [],
        places_taken=lambda event_id: 0,
        attendee_emails=lambda event_id: {},
        event_venue_capacity=lambda event_id: 120,
    ))

    info = service.registration_info("e1", "o1", ("event_organiser",))

    assert info["venue_capacity"] == 120


# AC23-N2 (negative): a failed venue lookup only hides the hint; the list still loads
def test_registration_info_survives_a_venue_lookup_failure() -> None:
    def fail(event_id: str) -> None:
        raise SupabaseRepositoryError("down")

    event = {"id": "e1", "organiser_id": "o1", "registration_capacity": 5, "status": "Confirmed"}
    service = RegistrationService(SimpleNamespace(
        get_event_access=lambda event_id: event,
        list_for_event=lambda event_id: [],
        places_taken=lambda event_id: 0,
        attendee_emails=lambda event_id: {},
        event_venue_capacity=fail,
    ))

    assert service.registration_info("e1", "o1", ("event_organiser",))["venue_capacity"] is None


# ---- Hotfix 24: the Coordinator changes the Event Organiser (Q&A #59, #61) ---------------


def change_organiser(client: Any, event: str, caller: str, **body: Any) -> Any:
    payload = {"organiser_email": "new@example.test", "reason": "Left the company", **body}
    with client:
        return client.post(
            f"/event-requests/{event}/organiser", headers=headers(caller), json=payload)


# AC24-H1 (happy): the assigned Coordinator hands a planning event to another Organiser
def test_coordinator_changes_the_organiser() -> None:
    client, repository, event = make_assigned_client(status="Planning")
    old = repository.rows[event]["organiser_id"]

    response = change_organiser(client, event, "coord-1")

    assert response.status_code == 200, response.text
    assert response.json()["organiser_id"] == "organiser-2"
    assert old != "organiser-2"


# AC24-N1 (negative): each refusal has its own status and changes nothing
@pytest.mark.parametrize(
    ("caller", "status", "body", "code"),
    [
        ("coord-2", "Planning", {}, 403),
        ("coord-1", "Cancelled", {}, 409),
        ("coord-1", "Draft", {}, 409),
        ("coord-1", "Planning", {"organiser_email": "nobody@example.test"}, 422),
        ("coord-1", "Planning", {"organiser_email": "gone@example.test"}, 422),
        ("coord-1", "Planning", {"reason": "   "}, 422),
        ("coord-1", "Planning", {"organiser_email": "not-an-email"}, 422),
    ],
    ids=["AC24-N1a", "AC24-N1b", "AC24-N1c", "AC24-N1d", "AC24-N1e", "AC24-N1f", "AC24-N1g"],
)
def test_organiser_change_refusals(caller: str, status: str, body: dict[str, Any], code: int) -> None:
    client, repository, event = make_assigned_client(status=status)
    before = repository.rows[event]["organiser_id"]

    response = change_organiser(client, event, caller, **body)

    assert response.status_code == code, response.text
    assert repository.rows[event]["organiser_id"] == before


# AC24-H2 (happy): both the new and the previous Organiser are told, once each
def test_organiser_change_tells_both_people() -> None:
    repository = SimpleNamespace(
        get_by_id=lambda event_id: {"organiser_id": "o-old"},
        change_organiser=lambda *args: {**EVENT_ROW, "organiser_id": "o-new", "status": "Planning"},
    )
    spy = Spy()
    service = EventTransitionService(EventRequestService(repository, spy), spy)

    service.change_organiser("e1", "coord-1", "new@example.test", "Left")

    notices = [(call["recipient_id"], call["became_organiser"]) for _, call in spy.calls]
    assert notices == [("o-new", True), ("o-old", False)]


# AC24-N2 (negative): a refused change tells nobody
def test_refused_organiser_change_tells_nobody() -> None:
    def refuse(*args: Any) -> None:
        raise EventRequestRpcError("x", errcode="P0006")

    spy = Spy()
    repository = SimpleNamespace(get_by_id=lambda event_id: {"organiser_id": "o-old"},
                                 change_organiser=refuse)
    service = EventTransitionService(EventRequestService(repository, spy), spy)

    with pytest.raises(OrganiserNotFoundError):
        service.change_organiser("e1", "coord-1", "nobody@example.test", "Left")
    assert spy.calls == []


# AC24-N3 (negative): the database's organisation refusal becomes a 409 for the Coordinator
def test_organisation_refusal_is_a_conflict() -> None:
    def refuse(*args: Any) -> None:
        raise EventRequestRpcError("x", errcode="P0007")

    repository = SimpleNamespace(get_by_id=lambda event_id: {}, change_organiser=refuse)
    service = EventTransitionService(EventRequestService(repository, Spy()), Spy())

    with pytest.raises(OrganiserOutsideOrganisationError) as caught:
        service.change_organiser("e1", "coord-1", "other@client.test", "Left")
    assert caught.value.status_code == 409


# AC24-N4 (negative): a failed read of the previous Organiser still changes the event
def test_organiser_change_survives_a_failed_previous_read() -> None:
    def fail(event_id: str) -> None:
        raise SupabaseRepositoryError("down")

    spy = Spy()
    repository = SimpleNamespace(
        get_by_id=fail,
        change_organiser=lambda *args: {**EVENT_ROW, "organiser_id": "o-new", "status": "Planning"},
    )
    service = EventTransitionService(EventRequestService(repository, spy), spy)

    saved = service.change_organiser("e1", "coord-1", "new@example.test", "Left")

    assert saved.organiser_id == "o-new"
    assert [call["recipient_id"] for _, call in spy.calls] == ["o-new"]
