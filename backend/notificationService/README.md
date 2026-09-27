# notificationService

Receives workflow events from the other services and turns them into
notifications for the people responsible for an event (SCRUM-37).

**Current state: scaffold.** The event contract below is live so other
services can integrate their hooks now, but events are only validated and
logged. Persistence, in-app delivery, email and the relevance rule are still
to be built.

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
| `event_id` | no | 1–64 characters. Will become the idempotency key once delivery is persisted, so a repeated event never notifies twice. Send one if you have one (for example the outbox event UUID). |

A malformed event gets `422`, so contract mistakes show up during development.

### Rules for callers

- **A notification must never break the action that caused it.** If this
  service is down or returns an error, log it and carry on. See
  `backend/eventRequestService/app/services/notification_client.py`.
- The endpoint is not authenticated yet. It is reachable inside the Compose
  network as `http://notification-service:8000/notifications/events`.

## Run locally

From the repository root, `docker compose up --build -d` starts it on
`http://localhost:8005` (API docs at `/docs`). Or, from this folder:

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
