"""SCRUM-39: Event Organiser access by client organisation (AC1-AC3, AC8).

Matrix: docs/testcases/scrum_39_testcases.md. Acme has Organisers A1 and A2,
Globex has B1, and NONE belongs to no organisation.
"""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_event_request_controller import (
    FakeCoordinatorAssignmentRepository,
    FakeEventRequestRepository,
    complete_payload,
)

from app.controllers import event_request_controller
from app.main import create_app

ACME = "aaaaaaaa-0000-4000-8000-000000000001"
GLOBEX = "bbbbbbbb-0000-4000-8000-000000000002"
A1 = "a1a1a1a1-1111-4111-8111-111111111111"
A2 = "a2a2a2a2-2222-4222-8222-222222222222"
B1 = "b1b1b1b1-3333-4333-8333-333333333333"
NONE = "00000000-4444-4444-8444-444444444444"

NON_DRAFT_STATUSES = [
    "Submitted",
    "Under Review",
    "Changes Requested",
    "Approved",
    "Planning",
    "Confirmed",
    "Completed",
    "Cancelled",
    "Rejected",
]


class OrganisationFakeRepository(FakeEventRequestRepository):
    """Adds organisation membership and mirrors the 0019 insert trigger,
    which stamps each new request with its organiser's organisation."""

    def __init__(self) -> None:
        super().__init__()
        self.members = {A1: ACME, A2: ACME, B1: GLOBEX}

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        row = super().create(values)
        organisation_id = self.members.get(row["organiser_id"])
        self.rows[row["id"]]["organisation_id"] = organisation_id
        return {**row, "organisation_id": organisation_id}

    def get_organisation_id(self, user_id: str) -> str | None:
        return self.members.get(user_id)

    def list_shared_with_organisation(
        self, organisation_id: str
    ) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in reversed(list(self.rows.values()))
            if row.get("organisation_id") == organisation_id
            and row["status"] != "Draft"
        ]


def client_for(
    repository: OrganisationFakeRepository,
    caller_id: str,
    roles: tuple[str, ...] = ("event_organiser",),
    coordinators: FakeCoordinatorAssignmentRepository | None = None,
) -> TestClient:
    application = create_app(repository, coordinators)
    caller = event_request_controller.AuthenticatedCaller(id=caller_id, roles=roles)
    application.dependency_overrides[
        event_request_controller.get_authenticated_caller
    ] = lambda: caller
    application.dependency_overrides[event_request_controller.get_organiser_id] = (
        lambda: caller_id
    )
    return TestClient(application)


def add_request(
    repository: OrganisationFakeRepository,
    organiser_id: str,
    status: str = "Submitted",
    name: str = "Acme Summit",
) -> str:
    return repository.create(
        {"organiser_id": organiser_id, "status": status, "event_name": name}
    )["id"]


def add_clarification(repository: OrganisationFakeRepository, request_id: str) -> None:
    repository.review_decision_rows.append(
        {
            "id": len(repository.review_decision_rows) + 1,
            "event_request_id": request_id,
            "coordinator_id": str(uuid4()),
            "decision_status": "Changes Requested",
            "reason": "Confirm the attendance",
            "decided_at": "2026-10-05T09:00:00+00:00",
            "organiser_response": None,
            "responded_at": None,
        }
    )


WRITE_ATTEMPTS = [
    ("PATCH", "", {"event_name": "Hijacked"}),
    ("POST", "/submit", complete_payload()),
    ("DELETE", "", None),
    ("POST", "/clarification-response", {"response": "Not mine to answer"}),
]


def attempt(client: TestClient, method: str, path: str, body: Any):
    return client.request(method, path, json=body)


# AC1-H1 (happy): the responsible Organiser still reads and edits their own Draft
def test_responsible_organiser_reads_and_edits_own_draft() -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1, status="Draft")

    with client_for(repository, A1) as client:
        fetched = client.get(f"/event-requests/{request_id}")
        updated = client.patch(
            f"/event-requests/{request_id}", json={"event_name": "Launch v2"}
        )

    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert repository.rows[request_id]["event_name"] == "Launch v2"


# AC2-H1 (happy): a same-organisation colleague can open a submitted request
def test_colleague_can_view_submitted_request() -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1)

    with client_for(repository, A2) as client:
        response = client.get(f"/event-requests/{request_id}")

    assert response.status_code == 200
    assert response.json()["id"] == request_id
    assert response.json()["organiser_id"] == A1
    assert response.json()["event_name"] == "Acme Summit"


# AC2-H2 (happy): the colleague's list has shared and own requests, newest first
def test_colleague_list_includes_shared_and_own_requests_newest_first() -> None:
    repository = OrganisationFakeRepository()
    shared = add_request(repository, A1, name="Shared")
    add_request(repository, B1, name="Globex only")
    own = add_request(repository, A2, status="Draft", name="Own draft")

    with client_for(repository, A2) as client:
        response = client.get("/event-requests")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [own, shared]


# AC2-P1 (partition): every write by a same-organisation viewer is refused with 403
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    WRITE_ATTEMPTS,
    ids=["AC2-P1a-patch", "AC2-P1b-submit", "AC2-P1c-delete", "AC2-P1d-clarify"],
)
def test_colleague_cannot_change_shared_request(
    method: str, suffix: str, body: Any
) -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1, status="Changes Requested")
    add_clarification(repository, request_id)
    before = dict(repository.rows[request_id])
    decisions_before = [dict(row) for row in repository.review_decision_rows]

    with client_for(repository, A2) as client:
        response = attempt(client, method, f"/event-requests/{request_id}{suffix}", body)

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}
    assert repository.rows[request_id] == before
    assert repository.review_decision_rows == decisions_before


# AC2-P2 (partition): one shared request per non-Draft status is visible
@pytest.mark.parametrize(
    "status", NON_DRAFT_STATUSES, ids=[f"AC2-P2-{s}" for s in NON_DRAFT_STATUSES]
)
def test_colleague_sees_shared_request_in_every_non_draft_status(status: str) -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1, status=status)

    with client_for(repository, A2) as client:
        listed = client.get("/event-requests")
        fetched = client.get(f"/event-requests/{request_id}")

    assert [row["id"] for row in listed.json()] == [request_id]
    assert fetched.status_code == 200
    assert fetched.json()["status"] == status


# AC2-P3 (partition): the colleague can read the shared request's decision history
def test_colleague_can_read_review_decisions() -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1, status="Changes Requested")
    add_clarification(repository, request_id)

    with client_for(repository, A2) as client:
        response = client.get(f"/event-requests/{request_id}/decisions")

    assert response.status_code == 200
    assert [row["reason"] for row in response.json()] == ["Confirm the attendance"]


# AC2-B1 (boundary): a colleague's Draft is not shared, in the list or directly
def test_colleague_draft_is_not_shared() -> None:
    repository = OrganisationFakeRepository()
    draft_id = add_request(repository, A1, status="Draft")

    with client_for(repository, A2) as client:
        listed = client.get("/event-requests")
        fetched = client.get(f"/event-requests/{draft_id}")
        patched = client.patch(
            f"/event-requests/{draft_id}", json={"event_name": "Hijacked"}
        )

    assert listed.json() == []
    assert fetched.status_code == 404
    assert patched.status_code == 404
    assert repository.rows[draft_id]["event_name"] == "Acme Summit"


# AC2-B2 (boundary): the request becomes visible once it moves Draft -> Submitted
def test_draft_becomes_visible_to_colleague_after_submission() -> None:
    repository = OrganisationFakeRepository()
    draft_id = add_request(repository, A1, status="Draft")

    with client_for(repository, A2) as colleague:
        before = colleague.get(f"/event-requests/{draft_id}")
    repository.rows[draft_id]["status"] = "Submitted"
    with client_for(repository, A2) as colleague:
        after = colleague.get(f"/event-requests/{draft_id}")

    assert before.status_code == 404
    assert after.status_code == 200


# AC2-X1 (cross-cutting): the organisation recorded at creation decides sharing
def test_recorded_organisation_not_current_membership_decides_sharing() -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1)
    repository.members[A1] = GLOBEX

    with client_for(repository, A2) as colleague:
        acme_view = colleague.get(f"/event-requests/{request_id}")
    with client_for(repository, B1) as outsider:
        globex_view = outsider.get(f"/event-requests/{request_id}")

    assert acme_view.status_code == 200
    assert globex_view.status_code == 404
    assert repository.rows[request_id]["organisation_id"] == ACME


# AC3-H1 (negative): an unrelated Organiser gets the same 404 as a missing request
def test_unrelated_organiser_cannot_tell_request_exists() -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1)

    with client_for(repository, B1) as client:
        existing = client.get(f"/event-requests/{request_id}")
        missing = client.get(f"/event-requests/{uuid4()}")
        listed = client.get("/event-requests")

    assert existing.status_code == 404
    assert existing.json() == missing.json()
    assert listed.json() == []


# AC3-P1 (partition): every access by an unrelated Organiser returns 404
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [*WRITE_ATTEMPTS, ("GET", "/decisions", None)],
    ids=[
        "AC3-P1a-patch",
        "AC3-P1b-submit",
        "AC3-P1c-delete",
        "AC3-P1d-clarify",
        "AC3-P1e-decisions",
    ],
)
def test_unrelated_organiser_gets_404_for_every_access(
    method: str, suffix: str, body: Any
) -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1, status="Changes Requested")
    add_clarification(repository, request_id)
    before = dict(repository.rows[request_id])
    decisions_before = [dict(row) for row in repository.review_decision_rows]

    with client_for(repository, B1) as client:
        response = attempt(client, method, f"/event-requests/{request_id}{suffix}", body)

    assert response.status_code == 404
    assert repository.rows[request_id] == before
    assert repository.review_decision_rows == decisions_before


# AC3-P2 (partition): an Organiser with no organisation sees only their own requests
def test_organiser_without_organisation_sees_only_own_requests() -> None:
    repository = OrganisationFakeRepository()
    acme_request = add_request(repository, A1)
    own = add_request(repository, NONE, name="Solo")

    with client_for(repository, NONE) as client:
        listed = client.get("/event-requests")
        fetched = client.get(f"/event-requests/{acme_request}")

    assert [row["id"] for row in listed.json()] == [own]
    assert fetched.status_code == 404


# AC3-P3 (partition): a request with no recorded organisation is shared with nobody
def test_request_without_organisation_is_not_shared() -> None:
    repository = OrganisationFakeRepository()
    request_id = add_request(repository, A1)
    repository.rows[request_id]["organisation_id"] = None

    with client_for(repository, A2) as colleague:
        colleague_view = colleague.get(f"/event-requests/{request_id}")
    with client_for(repository, A1) as owner:
        owner_view = owner.get(f"/event-requests/{request_id}")

    assert colleague_view.status_code == 404
    assert owner_view.status_code == 200


# AC8-X1 (cross-cutting): an unrelated Organiser who is the assigned Coordinator
# keeps coordinator access
def test_assigned_coordinator_access_survives_unrelated_organisation() -> None:
    repository = OrganisationFakeRepository()
    coordinators = FakeCoordinatorAssignmentRepository(repository)
    request_id = add_request(repository, A1)
    coordinators.create(
        {"event_request_id": request_id, "coordinator_id": B1, "assigned_by": A2}
    )

    with client_for(
        repository, B1, ("event_organiser", "event_coordinator"), coordinators
    ) as client:
        response = client.get(f"/event-requests/{request_id}")

    assert response.status_code == 200
    assert response.json()["id"] == request_id


# AC2-P4 (partition): the colleague can see whether a Coordinator is assigned
def test_colleague_can_read_coordinator_assignment() -> None:
    repository = OrganisationFakeRepository()
    coordinators = FakeCoordinatorAssignmentRepository(repository)
    request_id = add_request(repository, A1)
    coordinator_id = str(uuid4())
    coordinators.create(
        {
            "event_request_id": request_id,
            "coordinator_id": coordinator_id,
            "assigned_by": str(uuid4()),
        }
    )

    with client_for(repository, A2, coordinators=coordinators) as colleague:
        shared = colleague.get(f"/event-requests/{request_id}/coordinator")
    with client_for(repository, B1, coordinators=coordinators) as outsider:
        unrelated = outsider.get(f"/event-requests/{request_id}/coordinator")

    assert shared.status_code == 200
    assert shared.json()["coordinator_id"] == coordinator_id
    assert unrelated.status_code == 404
