"""SCRUM-19: the service's status pre-check runs before the database call.

FakeTechnicalSupportRepository mirrors the database functions' checks, so
the API tests prove the refusal itself (AC1-P4..P10, AC2-P4..P10). This
module proves where it happens: the service refuses a disallowed status
from its own rules module before any RPC call, while the locked database
functions stay the authoritative recheck (review finding #2).
"""

from typing import Any

from technical_support_fakes import (
    EVENT,
    REQ_AV,
    TSS_AV,
    FakeTechnicalSupportRepository,
    assignments_path,
    make_client,
    seed_event,
    seed_requirement,
)
from test_event_request_controller import FakeEventRequestRepository


class CountingRepository(FakeTechnicalSupportRepository):
    """Counts write RPCs without changing any of the fake's decisions."""

    def __init__(self, event_requests: FakeEventRequestRepository) -> None:
        super().__init__(event_requests)
        self.rpc_calls = 0

    def record_requirement(self, values: dict[str, Any]) -> dict[str, Any]:
        self.rpc_calls += 1
        return super().record_requirement(values)

    def assign(self, values: dict[str, Any]) -> dict[str, Any]:
        self.rpc_calls += 1
        return super().assign(values)


def seeded_repository(status: str) -> tuple[FakeEventRequestRepository,
                                             CountingRepository]:
    event_requests = FakeEventRequestRepository()
    seed_event(event_requests)
    event_requests.rows[EVENT]["status"] = status
    technical_support = CountingRepository(event_requests)
    seed_requirement(technical_support)
    return event_requests, technical_support


# AC2-N8 (negative): a refused status makes no database call — the service's
# pre-check refuses before the RPC, so production runs the rules module and
# the database never sees work it would refuse
def test_refused_status_makes_no_rpc_call() -> None:
    event_requests, technical_support = seeded_repository("Completed")

    with make_client(event_requests, technical_support) as client:
        response = client.post(
            assignments_path(EVENT, REQ_AV), json={"staff_id": TSS_AV}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "support_not_allowed"
    assert technical_support.rpc_calls == 0
    assert technical_support.assignment_rows == []
    assert event_requests.rows[EVENT]["status"] == "Completed"
