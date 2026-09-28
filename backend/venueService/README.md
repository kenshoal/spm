# venueService

FastAPI microservice for the venue catalogue and venue search / filtering.

## Scope

| Capability | Endpoints |
| --- | --- |
| Maintain the venue catalogue | `POST /venues`, `GET /venues/{id}`, `PATCH /venues/{id}`, `GET /venues` |
| Search and filter venues | `GET /venues/search` |

Venues are stored in the Supabase `public.venues` table
(`database/migrations/0016_venues.sql`) when `VENUE_STORAGE_BACKEND=supabase`,
which Docker Compose sets. The default, `memory`, keeps venues in process
memory and is used by the unit tests and standalone development; that data is
lost when the service stops. All routes verify the bearer token with `authService`; create and update
operations require the `venue_staff` role.

`GET /venues/search` accepts a `date` parameter but does not yet evaluate
per-date availability; a venue is excluded only when its whole-venue `status`
is not `available`. Per-date-slot blocking belongs to the venue availability
calendar / venue-blocking stories.

## Run locally

The standard project workflow is to run `docker compose up --build -d` from
the repository root. This exposes venueService on `http://localhost:8004`.
Use the commands below only when developing this service by itself.

To persist venues when running the service by itself, set
`VENUE_STORAGE_BACKEND=supabase`, `SUPABASE_URL` and the server-only
`SUPABASE_SECRET_KEY` (see `.env.example`).

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
