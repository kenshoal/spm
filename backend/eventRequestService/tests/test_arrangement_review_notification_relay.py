"""AC3 relay rules: prepared infrastructure snapshots plus the real HTTP sender."""

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest

from app.repositories import SupabaseRepositoryError
from app.services.arrangement_review_notification_relay import (
    ArrangementReviewNotificationRelay,
)
from app.services.notification_client import NotificationClient

URL = "https://notification.test/notifications/events"
FIRST_ACCEPTED = "2026-10-16T01:00:00Z"


def uid(number: int) -> str:
    return f"64000000-0000-4000-8000-{number:012d}"


def attempt(number=1, *, coordinator=None, staff=None, accepted=None):
    return {
        "review_id": uid(number),
        "payload": {
            "review_id": uid(number),
            "event_request_id": uid(100),
            "arrangement": "venue_booking",
            "arrangement_id": uid(200),
            "trigger_id": uid(300 + number),
            "trigger_type": "event_change",
            "changed_fields": ["expected_attendance"],
            "reason": "Attendance 25 -> 40; retain complete reason",
            "raised_at": FIRST_ACCEPTED,
            "cleared_at": None,
            "cleared_by": None,
        },
        "accepted_recipients": deepcopy(accepted or {}),
        "recipients_available": True,
        "coordinator_id": coordinator,
        "domain_recipient_ids": list(staff or []),
        "change_request_id": None,
    }


class PreparedRepository:
    """Records protocol calls; native SQL owns membership, acceptance and completion."""

    def __init__(self, snapshots, outcomes):
        self.snapshots = deepcopy(snapshots)
        self.outcomes = deepcopy(outcomes)
        self.rows = [{"review_id": key} for key in snapshots]
        self.begun = []
        self.accepted = []
        self.completed = []
        self.limits = []

    def list_pending(self, *, limit):
        self.limits.append(limit)
        return deepcopy(self.rows[:limit])

    def begin_attempt(self, review_id):
        self.begun.append(review_id)
        result = self.snapshots[review_id].pop(0)
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)

    def record_accepted(self, review_id, recipient_id):
        self.accepted.append((review_id, recipient_id))

    def complete_if_resolved(self, review_id):
        self.completed.append(review_id)
        return self.outcomes[review_id].pop(0)


def sender(monkeypatch, responses=None):
    responses = deepcopy(responses or {})
    captured = []

    def post(url, **kwargs):
        body = deepcopy(kwargs["json"])
        captured.append((url, body))
        prepared = responses.get(body["recipient_id"], [])
        result = prepared.pop(0) if prepared else 202
        if isinstance(result, Exception):
            raise result
        return httpx.Response(
            result, json={"status": "accepted"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", post)
    return NotificationClient(URL), captured


def expected_key(snapshot):
    payload = snapshot["payload"]
    return str(
        uuid5(
            NAMESPACE_URL,
            f"needs-review:{payload['trigger_id']}:{payload['arrangement_id']}",
        )
    )


# AC3-H1 (happy): each current deduplicated recipient receives the real cause and only accepted delivery is recorded.
def test_current_groups_overlap_once_and_preserve_actual_cause(monkeypatch):
    current = attempt(coordinator=uid(10), staff=[uid(10), uid(11)])
    repository = PreparedRepository({uid(1): [current]}, {uid(1): [True]})
    notifier, sent = sender(monkeypatch)
    completed = ArrangementReviewNotificationRelay(repository, notifier).relay_once()
    assert completed == 1
    assert repository.begun == [uid(1)]
    assert repository.limits == [50]
    assert sorted(repository.accepted) == [(uid(1), uid(10)), (uid(1), uid(11))]
    assert len(sent) == 2
    assert {body["recipient_id"] for _, body in sent} == {uid(10), uid(11)}
    for url, body in sent:
        assert url == URL
        assert body["event_type"] == "arrangement_needs_review"
        assert body["event_id"] == expected_key(current)
        assert body["payload"] == current["payload"]
        assert "change_request_id" not in body["payload"]
    assert current["accepted_recipients"] == {}


# AC3-N1 (negative): a retry keeps stable identity, honours current reassignment and never resends accepted former-only recipients.
def test_retry_uses_fresh_groups_and_keeps_accepted_recipient_evidence(monkeypatch):
    first = attempt(coordinator=uid(10), staff=[uid(11)])
    second = attempt(
        coordinator=uid(12), staff=[uid(11)], accepted={uid(10): FIRST_ACCEPTED}
    )
    repository = PreparedRepository({uid(1): [first, second]}, {uid(1): [False, True]})
    notifier, sent = sender(monkeypatch, {uid(11): [503, 202]})
    relay = ArrangementReviewNotificationRelay(repository, notifier)
    assert relay.relay_once() == 0
    assert relay.relay_once() == 1
    recipients = [body["recipient_id"] for _, body in sent]
    assert recipients.count(uid(10)) == 1
    assert recipients.count(uid(11)) == 2
    assert recipients.count(uid(12)) == 1
    assert {body["event_id"] for _, body in sent} == {expected_key(first)}
    assert sorted(repository.accepted) == [
        (uid(1), uid(10)),
        (uid(1), uid(11)),
        (uid(1), uid(12)),
    ]
    assert second["accepted_recipients"] == {uid(10): FIRST_ACCEPTED}


# AC3-N2 (negative): one recipient outage keeps its job pending while other recipients and later jobs still receive attempts.
def test_partial_service_failure_is_isolated_from_other_recipients_and_jobs(
    monkeypatch,
):
    first = attempt(coordinator=uid(10), staff=[uid(11)])
    later = attempt(2, coordinator=uid(12), staff=[uid(13)])
    repository = PreparedRepository(
        {uid(1): [first], uid(2): [later]}, {uid(1): [False], uid(2): [True]}
    )
    notifier, sent = sender(monkeypatch, {uid(10): [503]})
    assert ArrangementReviewNotificationRelay(repository, notifier).relay_once() == 1
    assert repository.begun == [uid(1), uid(2)]
    assert {body["recipient_id"] for _, body in sent} == {
        uid(10),
        uid(11),
        uid(12),
        uid(13),
    }
    assert sorted(repository.accepted) == [
        (uid(1), uid(11)),
        (uid(2), uid(12)),
        (uid(2), uid(13)),
    ]


# AC3-N3 (negative): an unexpected successful HTTP status is not the notification service's durable202 acceptance.
def test_http200_is_not_recorded_as_durable_acceptance(monkeypatch):
    current = attempt(coordinator=uid(10), staff=[uid(10)])
    repository = PreparedRepository({uid(1): [current]}, {uid(1): [False]})
    notifier, sent = sender(monkeypatch, {uid(10): [200]})
    assert ArrangementReviewNotificationRelay(repository, notifier).relay_once() == 0
    assert len(sent) == 1
    assert repository.accepted == []


@pytest.mark.parametrize(
    ("coordinator", "staff", "expected"),
    [(None, [uid(11)], [uid(11)]), (uid(10), [], [uid(10)])],
    ids=["AC3-B1", "AC3-B2"],
)
# AC3-B1, AC3-B2 (boundary): either absent required group leaves durable work unresolved even after the existing group accepts.
def test_missing_required_group_remains_pending(
    monkeypatch, coordinator, staff, expected
):
    current = attempt(coordinator=coordinator, staff=staff)
    repository = PreparedRepository({uid(1): [current]}, {uid(1): [False]})
    notifier, sent = sender(monkeypatch)
    assert ArrangementReviewNotificationRelay(repository, notifier).relay_once() == 0
    assert sorted(body["recipient_id"] for _, body in sent) == expected
    assert repository.accepted == [(uid(1), expected[0])]


# AC3-N4 (negative): an infrastructure failure in one attempt must not starve a later prepared deliverable job.
def test_attempt_failure_does_not_abort_remaining_batch(monkeypatch):
    later = attempt(2, coordinator=uid(12), staff=[uid(12)])
    repository = PreparedRepository(
        {uid(1): [SupabaseRepositoryError("private resolver outage")], uid(2): [later]},
        {uid(2): [True]},
    )
    notifier, sent = sender(monkeypatch)
    assert (
        ArrangementReviewNotificationRelay(
            repository, notifier, batch_size=2
        ).relay_once()
        == 1
    )
    assert repository.begun == [uid(1), uid(2)]
    assert repository.limits == [2]
    assert [body["recipient_id"] for _, body in sent] == [uid(12)]
    assert repository.accepted == [(uid(2), uid(12))]
