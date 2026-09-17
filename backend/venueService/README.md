# venueService

FastAPI microservice for the venue catalogue and venue search / filtering.

## Scope

| Capability | Endpoints |
| --- | --- |
| Maintain the venue catalogue | `POST /venues`, `GET /venues/{id}`, `PATCH /venues/{id}`, `GET /venues` |
| Search and filter venues | `GET /venues/search` |
| Create a venue block | `POST /venues/{venue_id}/blocks` |
| List a venue's blocks | `GET /venues/{venue_id}/blocks` |

Storage is an in-memory repository (`app/repository.py`) — a scaffold to be
replaced with a persistent backend once the project's database infrastructure
lands. Authorisation dependencies in `app/dependencies.py` are stubs pending
integration with `authService`.

`GET /venues/search` checks active venue blocks when a `date` is supplied.
Whole-venue status and the existing catalogue filters still apply.

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
affects dated search but does not change whole-venue status. Booking enforcement
and notifications are not yet integrated.

## Block retrieval and search (Day 4)

`GET /venues/{venue_id}/blocks` returns all blocks for that venue, including
lifted blocks, through the existing authenticated-user dependency. An existing
venue with no blocks returns `[]`; an unknown venue returns `404`.

Search behaviour:

- `GET /venues/search?date=2026-09-20&slot=AM` excludes venues with an active
  block covering AM on that date.
- With a date but no slot, a venue is returned if at least one of its operating
  slots remains unblocked. Separate blocks can collectively block all slots.
  A result does not mean the venue is available for the entire day.
- Without a date, dated blocks are not evaluated. A slot-only search checks
  normal operating slots, not availability on any specific date.
- Lifted blocks are ignored by search. Block dates include both boundaries;
  NIGHT belongs to its starting date. Only the venue's own blocks apply.

For the example above, September 20 AM search excludes the venue; NIGHT search
can include it if NIGHT is an operating slot and no other filter or block
excludes it. September 22 AM is outside this block and is unaffected by it.

These checks consider venue blocks only, not existing reservations. Storage
remains in memory, authentication remains stubbed, and there is no block-lifting
endpoint or calendar UI yet.

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
