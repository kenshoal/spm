# equipmentStatusService

Equipment status microservice (SCRUM-16). Owns status transitions on the `equipment` table and the `equipment_status_history` audit trail in Supabase. Each transition is a single atomic call to the `transition_equipment_status` Postgres function.

## Run locally

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8005
```

Requires `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `AUTH_SERVICE_URL` in the environment (or a `.env` file in the working directory; `AUTH_SERVICE_URL` defaults to `http://127.0.0.1:8001`).

The service is available at `http://localhost:8005`, its health check at `http://localhost:8005/health`, and interactive API documentation at `http://localhost:8005/docs`.

## Auth seam

Endpoints require an `Authorization: Bearer <token>` header whose access token is verified with authService (see `app/deps.py` and `docs/AUTH_INTEGRATION.md`). Requests without a valid token return 401; authenticated users without the `technical_support` role get 403 on transitions. `changed_by` on a transition is derived from the verified token server-side.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/equipment/{id}/status` | Current status plus computed `available` flag (only `AVAILABLE` is in service; any authenticated user) |
| PATCH | `/equipment/{id}/status` | Atomic transition (`technical_support` only): body `{ "new_status": ..., "reason": ... }`; records who/when in history |
| GET | `/equipment/{id}/status/history` | Audit trail, newest first (any authenticated user) |

Valid statuses: `AVAILABLE`, `DAMAGED`, `UNDER_REPAIR`, `UNDER_MAINTENANCE`, `RETIRED`.

## Test

```powershell
ruff check .
pytest
```
