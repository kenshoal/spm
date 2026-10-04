# notificationService

Receives workflow events from the other services and turns them into
notifications for the people responsible for an event (SCRUM-37).

**Current state:** events are stored as in-app notifications and each user can
read their own inbox. Email delivery, per-type channel settings and the
relevance rule are still to be built.

Requires migration
[`database/migrations/0017_notifications.sql`](../../database/migrations/0017_notifications.sql).

## Sending an event

`POST /notifications/events` → `202 Accepted` with `{"status": "accepted"}`.

```json
{
  "event_type": "coordinator_assigned",
  "recipient_id": "coord-1",
  "payload": {
    "event_request_id": "11111111-1111-4111-8111-111111111111",
    "coordinator_id": "coord-1",
    "assigned_by": "ops-1"
  },
  "event_id": "optional-idempotency-key"
}
```

| Field | Required | Rules |
| --- | --- | --- |
| `event_type` | yes | 1–100 characters |
| `recipient_id` | yes | 1–64 characters: the user to notify |
| `payload` | no | JSON object with event-specific details; defaults to `{}` |
| `event_id` | no | 1–64 characters. The idempotency key: an event repeated with the same `event_id` for the same recipient is stored once and the repeat still gets `202`. The same `event_id` may notify several recipients. Send one if you have one (for example the outbox event UUID). |

A malformed event gets `422`, so contract mistakes show up during development.
If the database is unreachable the answer is `502`; if Supabase is not
configured, `503`.

### Rules for callers

- **A notification must never break the action that caused it.** If this
  service is down or returns an error, log it and carry on. See
  `backend/eventRequestService/app/services/notification_client.py`.
- The endpoint is not authenticated yet. It is reachable inside the Compose
  network as `http://notification-service:8000/notifications/events`.

## Reading notifications

Both endpoints need `Authorization: Bearer <Supabase access token>`, checked
through authService's `/auth/me`. A user only ever sees their own
notifications.

To try them in `/docs`: get a token from authService's `POST /auth/login`
(http://localhost:8001/docs), click **Authorize** at the top of
http://localhost:8005/docs and paste the `access_token` alone (without
`Bearer`).

| Endpoint | Returns |
| --- | --- |
| `GET /notifications?unread_only=false&limit=50` | The caller's notifications, newest first. `limit` is 1–100. |
| `PATCH /notifications/{id}/read` | The notification, with `read_at` set. Marking it again keeps the first read time. Someone else's notification, or an unknown id, is `404`. |

Each notification is `{id, event_type, payload, read_at, created_at}`.

## Run locally

From the repository root, `docker compose up --build -d` starts it on
`http://localhost:8005` (API docs at `/docs`). Or, from this folder, copy
`.env.example` to `.env`, fill in the Supabase values, then:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8005
```

## Tests

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest
```

The tests fake Supabase. The table's own rules (one row per retried event, no
browser access) are checked by
[`database/verify_notifications.sql`](../../database/verify_notifications.sql).
