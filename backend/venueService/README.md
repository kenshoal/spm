# venueService

FastAPI microservice for the venue catalogue and venue search / filtering.

## Scope

| Capability | Endpoints |
| --- | --- |
| Maintain the venue catalogue | `POST /venues`, `GET /venues/{id}`, `PATCH /venues/{id}`, `GET /venues` |
| Search and filter venues | `GET /venues/search` |
| Create a venue block | `POST /venues/{venue_id}/blocks` |

Storage is an in-memory repository (`app/repository.py`) — a scaffold to be
replaced with a persistent backend once the project's database infrastructure
lands. Authorisation dependencies in `app/dependencies.py` are stubs pending
integration with `authService`.

`GET /venues/search` accepts a `date` parameter but does not yet evaluate
per-date availability; a venue is excluded only when its whole-venue `status`
is not `available`. Per-date-slot blocking belongs to the venue availability
calendar / venue-blocking stories.

## Create a venue block (Day 3)

Create a venue through `POST /venues` first, then use its returned ID in
`POST /venues/{venue_id}/blocks` with a body such as:

```json
{
  "start_date": "2026-09-20",
  "end_date": "2026-09-21",
  "slots": ["AM", "PM"],
  "reason_category": "maintenance",
  "reason_detail": "Air-conditioning repairs"
}
```

The selected slots apply on every date in the inclusive range. The endpoint
returns `201` with the saved block, its generated ID and timestamp, active
status, and creator from the staff dependency. Unknown venues return `404`;
invalid input (including client-supplied creator or status) returns `422`.

Blocks use `app/block_repository.py`, a temporary in-memory store with an
overridable FastAPI dependency. Both venues and blocks are local to the process
and lost on restart; venues stored only in Supabase are not visible here.
The staff dependency still returns a stub identity and does not enforce access.
Supabase persistence and real authentication are deferred. Creating a block
does not change whole-venue status or yet affect search, bookings, or notifications.

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

## Test

```powershell
ruff check .
pytest
```
