"""SCRUM-19: technical support requirements and assignments over HTTP.

The repository is faked (see technical_support_fakes.py) with the database
functions' check order; the real functions are proven by
database/verify_technical_support_assignments.sql.
"""

import pytest
from fastapi.testclient import TestClient
from technical_support_fakes import (
    ATTENDEE,
    COORD,
    EVENT,
    NOT_ALLOWED,
    OPS,
    ORGANISER,
    OTHER_COORD,
    OTHER_EVENT,
    REQ_AV,
    REQ_IT,
    REQ_OTHER,
    TSS_AV,
    TSS_AV2,
    TSS_LIGHT,
    USER_ROLES,
    VENUE_AV,
    FakeTechnicalSupportRepository,
    RecordingNotificationClient,
    assignments_path,
    candidates_path,
    make_client,
    requirements_path,
    seed_event,
    seed_requirement,
    technical_support_path,
)
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
)

from app.main import create_app
from app.repositories import SupabaseRepositoryError

ROLES = USER_ROLES

RECORD_BODY = {
    "description": "Two wireless mics and a mixing-desk operator for the keynote",
    "skill_tag": "audio_visual",
}


def seed_planning_event() -> FakeEventRequestRepository:
    event_requests = FakeEventRequestRepository()
    seed_event(event_requests)
    return event_requests


def seeded_assignment_fixture(
    notification: RecordingNotificationClient | None = None,
) -> tuple[FakeEventRequestRepository, FakeTechnicalSupportRepository,
           RecordingNotificationClient]:
    event_requests = seed_planning_event()
    technical_support = FakeTechnicalSupportRepository(event_requests)
    seed_requirement(technical_support)
    return event_requests, technical_support, notification or RecordingNotificationClient()


def seeded_view_fixture() -> tuple[FakeEventRequestRepository,
                                   FakeTechnicalSupportRepository]:
    event_requests, technical_support, _ = seeded_assignment_fixture()
    technical_support.assignment_rows.append(
        {
            "id": "bbbb0000-0000-4000-8000-000000000001",
            "requirement_id": REQ_AV,
            "event_request_id": EVENT,
            "staff_id": TSS_AV,
            "assigned_by": COORD,
            "assigned_at": "2030-03-01T09:30:00+00:00",
        }
    )
    return event_requests, technical_support


EXPECTED_VIEW = [
    {
        "id": REQ_AV,
        "event_request_id": EVENT,
        "description": "Two wireless mics and a mixing-desk operator for the keynote",
        "skill_tag": "audio_visual",
        "recorded_by": COORD,
        "recorded_at": "2030-03-01T09:00:00Z",
        "assigned_staff": [
            {
                "staff_id": TSS_AV,
                "assigned_by": COORD,
                "assigned_at": "2030-03-01T09:30:00Z",
            }
        ],
    }
]


# -- AC1: recording a requirement -----------------------------------------------


# AC1-H1 (happy): the assigned coordinator records a requirement on a Planning
# event and it shows on the event with nobody assigned
def test_coordinator_records_requirement() -> None:
    event_requests = seed_planning_event()
    technical_support = FakeTechnicalSupportRepository(event_requests)

    with make_client(event_requests, technical_support) as client:
        response = client.post(requirements_path(EVENT), json=RECORD_BODY)
        listed = client.get(technical_support_path(EVENT))

    assert response.status_code == 201
    body = response.json()
    assert body["event_request_id"] == EVENT
    assert body["description"] == RECORD_BODY["description"]
    assert body["skill_tag"] == "audio_visual"
    assert body["recorded_by"] == COORD
    assert body["recorded_at"]
    assert body["id"]
    view = listed.json()
    assert len(view) == 1
    assert view[0]["assigned_staff"] == []
    assert event_requests.rows[EVENT]["status"] == "Planning"


# AC1-P1..P3 (partition): each allowed status accepts a requirement
@pytest.mark.parametrize(
    "status", ["Approved", "Planning", "Confirmed"], ids=["AC1-P1", "AC1-P2", "AC1-P3"]
)
def test_requirement_accepted_from_allowed_statuses(status: str) -> None:
    event_requests = seed_planning_event()
    event_requests.rows[EVENT]["status"] = status

    with make_client(event_requests) as client:
        response = client.post(requirements_path(EVENT), json=RECORD_BODY)

    assert response.status_code == 201


@pytest.mark.parametrize("status", NOT_ALLOWED, ids=[f"AC1-P{4 + i}" for i in range(7)])
# AC1-P4..P10 (partition): every other status refuses, nothing stored
def test_requirement_refused_from_other_statuses(status: str) -> None:
    event_requests = seed_planning_event()
    technical_support = FakeTechnicalSupportRepository(event_requests)
    event_requests.rows[EVENT]["status"] = status

    with make_client(event_requests, technical_support) as client:
        response = client.post(requirements_path(EVENT), json=RECORD_BODY)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "support_not_allowed"
    assert technical_support.requirement_rows == []
    assert event_requests.rows[EVENT]["status"] == status


# AC1-N1 (negative): an unknown skill tag is refused
def test_unknown_skill_tag_is_refused() -> None:
    event_requests = seed_planning_event()

    with make_client(event_requests) as client:
        response = client.post(
            requirements_path(EVENT),
            json={"description": "Mics", "skill_tag": "plumbing"},
        )

    assert response.status_code == 422


# AC1-N3 (negative): a missing skill tag or missing description is refused
def test_missing_fields_are_refused() -> None:
    event_requests = seed_planning_event()

    with make_client(event_requests) as client:
        first = client.post(requirements_path(EVENT), json={"description": "Mics"})
        second = client.post(requirements_path(EVENT), json={"skill_tag": "lighting"})

    assert first.status_code == 422
    assert second.status_code == 422


# AC1-N4 (negative): a coordinator who is not on the event is told the event
# does not exist, not who holds it
def test_unrelated_coordinator_cannot_record() -> None:
    event_requests = seed_planning_event()

    with make_client(event_requests, caller_id=OTHER_COORD) as client:
        response = client.post(requirements_path(EVENT), json=RECORD_BODY)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "event_request_not_found"


# AC1-N5 (negative): an unknown event is not found
def test_unknown_event_cannot_record() -> None:
    with make_client() as client:
        response = client.post(
            requirements_path("99999999-9999-4999-8999-999999999999"),
            json=RECORD_BODY,
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "event_request_not_found"


# AC1-N6 (negative): the client cannot choose who recorded the requirement
def test_client_cannot_choose_recorded_by() -> None:
    event_requests = seed_planning_event()

    with make_client(event_requests) as client:
        response = client.post(
            requirements_path(EVENT), json={**RECORD_BODY, "recorded_by": OTHER_COORD}
        )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "caller",
    [ORGANISER, TSS_AV, VENUE_AV, OPS, ATTENDEE],
    ids=[
        "AC1-X1-organiser",
        "AC1-X1-tss",
        "AC1-X1-venue",
        "AC1-X1-ops",
        "AC1-X1-attendee",
    ],
)
# AC1-X1 (cross-cutting): no other role can record, not even the owning organiser
def test_other_roles_cannot_record(caller: str) -> None:
    event_requests = seed_planning_event()

    with make_client(
        event_requests, caller_id=caller, roles=ROLES[caller]
    ) as client:
        response = client.post(requirements_path(EVENT), json=RECORD_BODY)

    assert response.status_code == 403


# AC1-X2 (cross-cutting): a reassignment between page load and submit is caught
# at write time — the database function, here its fake, refuses the stale caller
def test_reassignment_between_load_and_record_is_caught() -> None:
    event_requests = seed_planning_event()
    technical_support = FakeTechnicalSupportRepository(event_requests)
    # Another coordinator is assigned after COORD loaded the page (higher id wins).
    event_requests.coordinator_assignment_rows.append(
        {
            "id": len(event_requests.coordinator_assignment_rows) + 1,
            "event_request_id": EVENT,
            "coordinator_id": OTHER_COORD,
            "assigned_by": OPS,
            "assigned_at": "2030-03-01T10:00:00+00:00",
        }
    )

    with make_client(event_requests, technical_support) as client:
        response = client.post(requirements_path(EVENT), json=RECORD_BODY)

    assert response.status_code == 404
    assert technical_support.requirement_rows == []


# AC1-B1, AC1-B2 (boundary): blank and whitespace-only descriptions are refused
@pytest.mark.parametrize("description", ["", "   \n\t"], ids=["AC1-B1", "AC1-B2"])
def test_blank_descriptions_are_refused(description: str) -> None:
    event_requests = seed_planning_event()

    with make_client(event_requests) as client:
        response = client.post(
            requirements_path(EVENT),
            json={"description": description, "skill_tag": "audio_visual"},
        )

    assert response.status_code == 422


# AC1-B4, AC1-B5 (boundary): 2000 characters is accepted, 2001 is refused
@pytest.mark.parametrize(
    ("length", "expected"), [(2000, 201), (2001, 422)], ids=["AC1-B4", "AC1-B5"]
)
def test_description_length_boundaries(length: int, expected: int) -> None:
    event_requests = seed_planning_event()

    with make_client(event_requests) as client:
        response = client.post(
            requirements_path(EVENT),
            json={"description": "x" * length, "skill_tag": "audio_visual"},
        )

    assert response.status_code == expected


# -- AC2: assigning staff --------------------------------------------------------


# AC2-H1 (happy): the coordinator assigns a suitable staff member
def test_coordinator_assigns_suitable_staff() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 201
    body = response.json()
    assert body["requirement_id"] == REQ_AV
    assert body["event_request_id"] == EVENT
    assert body["staff_id"] == TSS_AV
    assert body["assigned_by"] == COORD
    assert body["assigned_at"]
    assert len(technical_support.assignment_rows) == 1


# AC2-H2 (happy): several staff can be assigned to one requirement
def test_several_staff_can_be_assigned() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        first = client.post(assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV})
        second = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV2}
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert len(technical_support.assignment_rows) == 2


@pytest.mark.parametrize(
    "status", ["Approved", "Planning", "Confirmed"], ids=["AC2-P1", "AC2-P2", "AC2-P3"]
)
# AC2-P1..P3 (partition): each allowed status accepts an assignment
def test_assignment_accepted_from_allowed_statuses(status: str) -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()
    event_requests.rows[EVENT]["status"] = status

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 201


@pytest.mark.parametrize("status", NOT_ALLOWED, ids=[f"AC2-P{4 + i}" for i in range(7)])
# AC2-P4..P10 (partition): a status that no longer allows support refuses, and
# a requirement recorded earlier stays without assignments
def test_assignment_refused_from_other_statuses(status: str) -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()
    event_requests.rows[EVENT]["status"] = status

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "support_not_allowed"
    assert technical_support.assignment_rows == []


# AC2-N1 (negative): a requirement that belongs to another event is refused
def test_requirement_on_another_event_is_refused() -> None:
    event_requests = seed_planning_event()
    seed_event(event_requests, event_id=OTHER_EVENT)
    technical_support = FakeTechnicalSupportRepository(event_requests)
    seed_requirement(technical_support, requirement_id=REQ_OTHER, event_id=OTHER_EVENT)

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_OTHER), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "requirement_not_found"
    assert technical_support.assignment_rows == []


# AC2-N2 (negative): an unknown requirement id is not found
def test_unknown_requirement_is_not_found() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, "aaaa0000-0000-4000-8000-0000000000ff"),
            json={"staff_id": TSS_AV},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "requirement_not_found"


# AC2-N3 (negative): the same person twice is refused, one row and one
# notification remain
def test_repeat_assignment_is_refused() -> None:
    event_requests, technical_support, notification = seeded_assignment_fixture()

    with make_client(event_requests, technical_support, notification) as client:
        first = client.post(assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV})
        second = client.post(assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV})

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "already_assigned"
    assert len(technical_support.assignment_rows) == 1
    assert len(notification.calls) == 1


# AC2-N4 (negative): a coordinator who is not on the event cannot assign
def test_unrelated_coordinator_cannot_assign() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(
        event_requests, technical_support, caller_id=OTHER_COORD
    ) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "event_request_not_found"
    assert technical_support.assignment_rows == []


# AC2-N5 (negative): a reassignment between page load and assign is caught at
# write time by the database function's latest-coordinator check
def test_reassignment_between_load_and_assign_is_caught() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()
    event_requests.coordinator_assignment_rows.append(
        {
            "id": len(event_requests.coordinator_assignment_rows) + 1,
            "event_request_id": EVENT,
            "coordinator_id": OTHER_COORD,
            "assigned_by": OPS,
            "assigned_at": "2030-03-01T10:00:00+00:00",
        }
    )

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 404
    assert technical_support.assignment_rows == []


# AC2-N7 (negative): an unavailable database is a 502 and notifies nobody
def test_repository_failure_is_a_bad_gateway() -> None:
    event_requests, _, notification = seeded_assignment_fixture()

    class DownRepository(FakeTechnicalSupportRepository):
        def assign(self, values: dict) -> dict:  # type: ignore[override]
            raise SupabaseRepositoryError("down")

    technical_support = DownRepository(event_requests)
    seed_requirement(technical_support)

    with make_client(event_requests, technical_support, notification) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 502
    assert technical_support.assignment_rows == []
    assert notification.calls == []


@pytest.mark.parametrize(
    ("staff_id", "expected"),
    [("", 422), ("s" * 64, 409), ("s" * 65, 422)],
    ids=["AC2-B1", "AC2-B2", "AC2-B3"],
)
# AC2-B1..B3 (boundary): staff id length — blank refused, 64 passes validation
# and fails suitability, 65 refused
def test_staff_id_length_boundaries(staff_id: str, expected: int) -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": staff_id}
        )

    assert response.status_code == expected


@pytest.mark.parametrize(
    "caller",
    [ORGANISER, TSS_AV, VENUE_AV, OPS, ATTENDEE],
    ids=[
        "AC2-X1-organiser",
        "AC2-X1-tss-self",
        "AC2-X1-venue",
        "AC2-X1-ops",
        "AC2-X1-attendee",
    ],
)
# AC2-X1 (cross-cutting): no other role can assign, not even a TSS assigning
# themselves
def test_other_roles_cannot_assign(caller: str) -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(
        event_requests, technical_support, caller_id=caller, roles=ROLES[caller]
    ) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": caller}
        )

    assert response.status_code == 403
    assert technical_support.assignment_rows == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", f"/event-requests/{EVENT}/technical-support/requirements"),
        ("get", f"/event-requests/{EVENT}/technical-support"),
        (
            "get",
            f"/event-requests/{EVENT}/technical-support/requirements/{REQ_AV}/candidates",
        ),
        (
            "post",
            f"/event-requests/{EVENT}/technical-support/requirements/{REQ_AV}/assignments",
        ),
    ],
    ids=["record", "view", "candidates", "assign"],
)
# AC2-X2 (cross-cutting): no session is a 401 on every technical support endpoint
def test_endpoints_require_a_session(method: str, path: str) -> None:
    event_requests = seed_planning_event()
    technical_support = FakeTechnicalSupportRepository(event_requests)
    application = create_app(
        event_requests,
        FakeCoordinatorAssignmentRepository(event_requests),
        technical_support_repository=technical_support,
    )

    with TestClient(application) as client:
        if method == "post":
            body = (
                RECORD_BODY
                if path.endswith("requirements")
                else {"staff_id": TSS_AV}
            )
            response = client.post(path, json=body)
        else:
            response = client.get(path)

    assert response.status_code == 401


# AC2-X3 (negative): the client cannot choose who assigned the staff member
def test_client_cannot_choose_assigned_by() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV),
            json={"staff_id": TSS_AV, "assigned_by": OTHER_COORD},
        )

    assert response.status_code == 422


# -- AC3: suitability -------------------------------------------------------------


# AC3-H1 (happy): the candidate list shows exactly the suitable staff, ascending,
# with the person already on the requirement marked
def test_candidate_list_shows_exactly_suitable_staff() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()
    technical_support.assignment_rows.append(
        {
            "id": "bbbb0000-0000-4000-8000-000000000001",
            "requirement_id": REQ_AV,
            "event_request_id": EVENT,
            "staff_id": TSS_AV,
            "assigned_by": COORD,
            "assigned_at": "2030-03-01T09:30:00+00:00",
        }
    )

    with make_client(event_requests, technical_support) as client:
        response = client.get(candidates_path(EVENT, REQ_AV))

    assert response.status_code == 200
    assert response.json() == [
        {"staff_id": TSS_AV, "already_assigned": True},
        {"staff_id": TSS_AV2, "already_assigned": False},
    ]


# AC3-P2 (negative): a TSS with the wrong tag is refused as not suitable
def test_wrong_tag_is_not_suitable() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_LIGHT}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "staff_not_suitable"
    assert technical_support.assignment_rows == []


# AC3-P4 (negative): the skill tag without the technical_support role is not
# suitable
def test_tag_without_role_is_not_suitable() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": VENUE_AV}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "staff_not_suitable"
    assert technical_support.assignment_rows == []


# AC3-N1 (negative): an unknown user id is "not suitable", not "not found", so
# the response does not reveal whether the account exists
def test_unknown_user_is_not_suitable() -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": "ghost-user"}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "staff_not_suitable"
    assert technical_support.assignment_rows == []


# AC3-X1 (cross-cutting): no availability or double-booking check — a staff
# member on another event at the same time stays assignable
def test_no_double_booking_check() -> None:
    event_requests = seed_planning_event()
    seed_event(event_requests, event_id=OTHER_EVENT)
    technical_support = FakeTechnicalSupportRepository(event_requests)
    seed_requirement(technical_support)
    seed_requirement(technical_support, requirement_id=REQ_OTHER, event_id=OTHER_EVENT)
    technical_support.assignment_rows.append(
        {
            "id": "bbbb0000-0000-4000-8000-000000000001",
            "requirement_id": REQ_OTHER,
            "event_request_id": OTHER_EVENT,
            "staff_id": TSS_AV,
            "assigned_by": COORD,
            "assigned_at": "2030-03-01T09:30:00+00:00",
        }
    )

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 201
    assert len(technical_support.assignment_rows) == 2


@pytest.mark.parametrize(
    ("caller", "expected"),
    [(OTHER_COORD, 404), (TSS_AV, 403), (ORGANISER, 403), (OPS, 403)],
    ids=["AC3-X3-other-coord", "AC3-X3-tss", "AC3-X3-organiser", "AC3-X3-ops"],
)
# AC3-X3 (cross-cutting): only the event's coordinator may list candidates
def test_candidate_list_access(caller: str, expected: int) -> None:
    event_requests, technical_support, _ = seeded_assignment_fixture()

    with make_client(
        event_requests, technical_support, caller_id=caller, roles=ROLES[caller]
    ) as client:
        response = client.get(candidates_path(EVENT, REQ_AV))

    assert response.status_code == expected


# -- AC4: the event shows its assigned staff --------------------------------------


# AC4-H1 (happy): the coordinator sees who is assigned, by whom and when
def test_coordinator_sees_assigned_staff() -> None:
    event_requests, technical_support = seeded_view_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.get(technical_support_path(EVENT))

    assert response.status_code == 200
    assert response.json() == EXPECTED_VIEW


# AC4-X1 (cross-cutting): the view returns exactly the agreed fields — nothing
# beyond the requirement and its assigned staff
def test_view_returns_exactly_the_agreed_keys() -> None:
    event_requests, technical_support = seeded_view_fixture()

    with make_client(event_requests, technical_support) as client:
        response = client.get(technical_support_path(EVENT))

    body = response.json()
    assert set(body[0]) == {
        "id",
        "event_request_id",
        "description",
        "skill_tag",
        "recorded_by",
        "recorded_at",
        "assigned_staff",
    }
    assert set(body[0]["assigned_staff"][0]) == {"staff_id", "assigned_by", "assigned_at"}
    assert "organiser" not in response.text


# AC4-H2 (happy): any Technical Support Staff member sees the same view
def test_any_technical_support_sees_the_view() -> None:
    event_requests, technical_support = seeded_view_fixture()

    with make_client(
        event_requests,
        technical_support,
        caller_id=TSS_LIGHT,
        roles=("technical_support",),
    ) as client:
        response = client.get(technical_support_path(EVENT))

    assert response.status_code == 200
    assert response.json() == EXPECTED_VIEW


# AC4-P1 (partition): a requirement with nobody assigned shows an empty list
def test_unstaffed_requirement_shows_empty_list() -> None:
    event_requests, technical_support = seeded_view_fixture()
    seed_requirement(
        technical_support,
        requirement_id=REQ_IT,
        skill_tag="it_network",
        description="Venue Wi-Fi for 300 delegates",
    )

    with make_client(event_requests, technical_support) as client:
        response = client.get(technical_support_path(EVENT))

    body = response.json()
    av = next(row for row in body if row["id"] == REQ_AV)
    it = next(row for row in body if row["id"] == REQ_IT)
    assert len(av["assigned_staff"]) == 1
    assert it["assigned_staff"] == []


# AC4-P3 (partition): an event with no requirements shows an empty list
def test_event_without_requirements_shows_empty_list() -> None:
    event_requests = seed_planning_event()
    technical_support = FakeTechnicalSupportRepository(event_requests)

    with make_client(event_requests, technical_support) as client:
        response = client.get(technical_support_path(EVENT))

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("caller", "expected"),
    [
        (OTHER_COORD, 404),
        (ORGANISER, 403),
        (VENUE_AV, 403),
        (OPS, 403),
        (ATTENDEE, 403),
    ],
    ids=[
        "AC4-N1-other-coord",
        "AC4-N1-organiser",
        "AC4-N1-venue",
        "AC4-N1-ops",
        "AC4-N1-attendee",
    ],
)
# AC4-N1 (negative): an unrelated coordinator is told nothing; every other role
# without the relationship is refused
def test_view_access(caller: str, expected: int) -> None:
    event_requests, technical_support = seeded_view_fixture()

    with make_client(
        event_requests, technical_support, caller_id=caller, roles=ROLES[caller]
    ) as client:
        response = client.get(technical_support_path(EVENT))

    assert response.status_code == expected


# AC4-N1 (negative): an unknown event is not found for its coordinator
def test_unknown_event_view_is_not_found() -> None:
    with make_client() as client:
        response = client.get(
            technical_support_path("99999999-9999-4999-8999-999999999999")
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "event_request_not_found"


# -- AC5: notifications ------------------------------------------------------------


# AC5-H1 (happy): a successful assignment notifies exactly the new staff member,
# naming the event and the requirement
def test_assignment_notifies_the_staff_member() -> None:
    event_requests, technical_support, notification = seeded_assignment_fixture()

    with make_client(event_requests, technical_support, notification) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 201
    assert notification.calls == [
        {
            "assignment_id": response.json()["id"],
            "event_request_id": EVENT,
            "event_name": "Tech Summit 2030",
            "requirement_id": REQ_AV,
            "skill_tag": "audio_visual",
            "staff_id": TSS_AV,
            "assigned_by": COORD,
        }
    ]


# AC5-H2 (happy): only the newly assigned person is notified
def test_only_the_new_staff_member_is_notified() -> None:
    event_requests, technical_support, notification = seeded_assignment_fixture()

    with make_client(event_requests, technical_support, notification) as client:
        client.post(assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV})
        client.post(assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV2})

    assert [call["staff_id"] for call in notification.calls] == [TSS_AV, TSS_AV2]


# AC5-N2 (negative): a notification failure never undoes the assignment
def test_notification_failure_keeps_the_assignment() -> None:
    event_requests, technical_support, notification = seeded_assignment_fixture()
    notification.fail = True

    with make_client(event_requests, technical_support, notification) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 201
    assert len(technical_support.assignment_rows) == 1


@pytest.mark.parametrize(
    "mode",
    [
        "support_not_allowed",
        "staff_not_suitable",
        "already_assigned",
        "unrelated_coordinator",
        "wrong_requirement",
        "wrong_role",
        "database_down",
    ],
    ids=[
        "AC5-N1-409-status",
        "AC5-N1-409-suitable",
        "AC5-N1-409-duplicate",
        "AC5-N1-404-coordinator",
        "AC5-N1-404-requirement",
        "AC5-N1-403-role",
        "AC5-N1-502-database",
    ],
)
# AC5-N1 (negative): a refused assignment notifies nobody, whatever the refusal
def test_refused_assignment_notifies_nobody(mode: str) -> None:
    event_requests, technical_support, notification = seeded_assignment_fixture()
    caller, roles = COORD, ROLES[COORD]
    staff = TSS_AV
    requirement_id = REQ_AV

    if mode == "support_not_allowed":
        event_requests.rows[EVENT]["status"] = "Completed"
    elif mode == "staff_not_suitable":
        staff = TSS_LIGHT
    elif mode == "already_assigned":
        with make_client(event_requests, technical_support, notification) as client:
            client.post(assignments_path(EVENT, REQ_AV), json={"staff_id": staff})
        notification.calls.clear()
    elif mode == "unrelated_coordinator":
        caller, roles = OTHER_COORD, ROLES[OTHER_COORD]
    elif mode == "wrong_requirement":
        requirement_id = "aaaa0000-0000-4000-8000-0000000000ff"
    elif mode == "wrong_role":
        caller, roles = OPS, ROLES[OPS]

    repository = technical_support
    if mode == "database_down":

        class DownRepository(FakeTechnicalSupportRepository):
            def assign(self, values: dict) -> dict:  # type: ignore[override]
                raise SupabaseRepositoryError("down")

        repository = DownRepository(event_requests)
        seed_requirement(repository)

    with make_client(
        event_requests, repository, notification, caller_id=caller, roles=roles
    ) as client:
        response = client.post(
            assignments_path(EVENT, requirement_id), json={"staff_id": staff}
        )

    assert response.status_code >= 400
    assert notification.calls == []
