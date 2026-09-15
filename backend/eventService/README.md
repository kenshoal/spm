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

## Database

Data lives in the team's shared Supabase Postgres project. Each
microservice owns its own schema there rather than a separate database —
this service's tables live under `event_service`, not `public`.

Copy `.env.example` to `.env` and fill in `DATABASE_URL` from the Supabase
project's **Connect** panel — use the **Session pooler** string (port 5432,
user `postgres.<project-ref>`), not Direct connection: this project doesn't
have a direct-connection host provisioned, only the pooler. `.env` is
gitignored — never commit real credentials.

The schema and tables don't exist until you create them — there's no
migration tooling in this repo yet, so run this once (and again any time
models change, it's idempotent):

```powershell
python -m app.init_db
```

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

Without a configured `DATABASE_URL`, it falls back to a local Postgres at
`postgresql+psycopg://event:event@localhost:5432/event` — useful for a
quick check without touching the shared database, but most local dev
should point at Supabase via `.env`.

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
