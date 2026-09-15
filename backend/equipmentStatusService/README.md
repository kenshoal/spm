# equipmentStatusService

Equipment status microservice (SCRUM-16). Owns status transitions on the `equipment` table and the `equipment_status_history` audit trail in Supabase. Each transition is a single atomic call to the `transition_equipment_status` Postgres function.

## Run locally

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8003
```

Requires `SUPABASE_URL` and `SUPABASE_SECRET_KEY` in the environment (or a `.env` file in the working directory).

The service is available at `http://localhost:8003`, its health check at `http://localhost:8003/health`, and interactive API documentation at `http://localhost:8003/docs`.

## Auth seam

Endpoints require an `X-User-Id` header (stubbed auth — see `app/deps.py` and `docs/AUTH_INTEGRATION.md`). Requests without it return 401. `changed_by` on a transition is derived from that header server-side.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/equipment/{id}/status` | Current status plus computed `available` flag (only `AVAILABLE` is in service) |
| PATCH | `/equipment/{id}/status` | Atomic transition: body `{ "new_status": ..., "reason": ... }`; records who/when in history |
| GET | `/equipment/{id}/status/history` | Audit trail, newest first |

Valid statuses: `AVAILABLE`, `DAMAGED`, `UNDER_REPAIR`, `UNDER_MAINTENANCE`, `RETIRED`.

## Test

```powershell
ruff check .
pytest
```
