# eventService

FastAPI event microservice: owns the event-status state machine (Draft →
Submitted → Under Review → Changes Requested / Approved / Rejected →
Planning → Confirmed → Completed, with Cancelled reachable from any
non-terminal status).

- `app/status.py` — the pure state-transition rules, no FastAPI or DB.
- `app/dependencies.py` — caller identity, stubbed on `X-User-Id` /
  `X-User-Role` headers until authService issues real tokens.
- `app/routers/events.py` — create/read/discard an event, and the
  `POST /events/{id}/status` transition action.

## Run locally

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The service is available at `http://localhost:8000`, its health check at
`http://localhost:8000/health`, and interactive API documentation at
`http://localhost:8000/docs`.

By default it connects to Postgres at
`postgresql+psycopg://event:event@localhost:5432/event`; override with the
`DATABASE_URL` environment variable.

## Test

```powershell
ruff check .
pytest
```

Tests run against an in-memory SQLite database (see
`tests/test_events_api.py`), so no running Postgres is required.

## Calling the API

Every request needs `X-User-Id` and `X-User-Role` headers
(`organiser` or `event_coordinator`) until real auth is wired in:

```powershell
curl -X POST http://localhost:8000/events `
  -H "X-User-Id: org-1" -H "X-User-Role: organiser" `
  -H "Content-Type: application/json" `
  -d '{\"title\": \"Orientation\"}'
```
