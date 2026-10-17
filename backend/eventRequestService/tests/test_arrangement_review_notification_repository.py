"""Approved AC3 delivery protocol through the real HTTP adapter, not PostgREST."""

import json

import httpx

from app.repositories.arrangement_review_notification_repository import (
    SupabaseArrangementReviewNotificationRepository,
)


# AC3-X4 (cross-cutting): durable relay calls must preserve fair pending selection and exact bounded RPC arguments.
def test_real_delivery_adapter_wire_contract():
    review = "64000000-0000-4000-8000-000000000001"
    recipient = "64000000-0000-4000-8000-000000000010"
    snapshot = {
        "review_id": review,
        "payload": {"reason": "Attendance 25 to 40"},
        "accepted_recipients": {},
        "recipients_available": True,
        "coordinator_id": recipient,
        "domain_recipient_ids": [recipient],
        "change_request_id": None,
    }
    calls = []

    def transport(request):
        calls.append(request)
        assert request.headers["apikey"] == "sb_secret_test"
        assert request.headers.get("accept") != "application/vnd.pgrst.object+json"
        if len(calls) == 1:
            assert request.method == "GET"
            assert request.url.path == "/rest/v1/arrangement_review_notification_outbox"
            assert dict(request.url.params) == {
                "published_at": "is.null",
                "order": "last_attempted_at.asc.nullsfirst,occurred_at.asc,review_id.asc",
                "limit": "7",
                "select": "review_id",
            }
            return httpx.Response(200, json=[{"review_id": review}])
        assert request.method == "POST"
        assert dict(request.url.params) == {}
        if len(calls) == 2:
            assert request.url.path == "/rest/v1/rpc/begin_arrangement_review_notification_attempt"
            assert json.loads(request.content) == {"p_review_id": review}
            return httpx.Response(200, json=snapshot)
        if len(calls) == 3:
            assert request.url.path == "/rest/v1/rpc/record_arrangement_review_notification_accepted"
            assert json.loads(request.content) == {"p_review_id": review, "p_recipient_id": recipient}
            return httpx.Response(204)
        assert request.url.path == "/rest/v1/rpc/complete_arrangement_review_notification"
        assert json.loads(request.content) == {"p_review_id": review}
        return httpx.Response(200, json=True)

    repository = SupabaseArrangementReviewNotificationRepository(
        "https://project.supabase.co", "sb_secret_test", transport=httpx.MockTransport(transport)
    )
    try:
        assert repository.list_pending(limit=7) == [{"review_id": review}]
        assert repository.begin_attempt(review) == snapshot
        assert repository.record_accepted(review, recipient) is None
        assert repository.complete_if_resolved(review) is True
        assert len(calls) == 4
    finally:
        repository.close()
