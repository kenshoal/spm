# eventService

FastAPI coordinator-assignment microservice. Event creation, drafting, and
status all belong to **eventRequestService** — this service owns exactly
one thing: which Event Coordinator is assigned to a submitted event
request, and the history of who's been assigned.

- `app/models.py` — `EventRequestRef` (a **read-only mirror** of
  eventRequestService's `event_requests` table — never created or altered
  here) and `EventCoordinatorAssignment` (this service's own table; one
  row per assignment, so reassigning preserves history instead of
  overwriting it).
- `app/dependencies.py` — caller identity, stubbed on `X-User-Id` /
  `X-User-Role` headers until authService issues real tokens.
- `app/routers/assignments.py` — `POST /event-requests/{id}/coordinator`
  (assign/reassign, Operations-Manager-only) and
  `GET /event-requests/{id}/coordinator` (current assignment — this is
  what eventRequestService's status logic should call to check "is the
  caller the assigned Coordinator" before allowing cancel/complete).

## Database

Data lives in the team's shared Supabase Postgres project, in the default
`public` schema — same database eventRequestService and other services
use (an earlier "one schema per microservice" plan didn't end up being
what the team actually built against).

Copy `.env.example` to `.env` and fill in `DATABASE_URL` from the Supabase
project's **Connect** panel — use the **Session pooler** string (port 5432,
user `postgres.<project-ref>`), not Direct connection: this project doesn't
have a direct-connection host provisioned, only the pooler. `.env` is
gitignored — never commit real credentials.

This service's table doesn't exist until you create it — there's no
migration tooling in this repo yet, so run this once (and again any time
the model changes, it's idempotent). It only ever touches
`event_coordinator_assignments`, never `event_requests` (not this
service's table to create or alter):

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

Tests run against an in-memory SQLite database (see `tests/conftest.py`),
so no running Postgres is required. Since `event_requests` belongs to
eventRequestService, tests seed a stand-in row directly
(`conftest.seed_event_request`) rather than creating one through this
service's own API — it doesn't have one.

## Calling the API

Every request needs `X-User-Id` and `X-User-Role` headers
(`operations_manager` to assign; any role to read) until real auth is
wired in:

```powershell
curl -X POST http://localhost:8000/event-requests/<event-request-id>/coordinator `
  -H "X-User-Id: ops-1" -H "X-User-Role: operations_manager" `
  -H "Content-Type: application/json" `
  -d '{\"coordinator_id\": \"coord-1\"}'
```
