# equipmentService

Equipment catalogue & status microservice (SCRUM-16, SCRUM-45). Reads/writes the `equipment` table in Supabase, seeds the first `equipment_status_history` row on create, and performs status transitions atomically via the `transition_equipment_status` Postgres function.

## Run locally

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8002
```

Requires `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `AUTH_SERVICE_URL` in the environment (or a `.env` file in the working directory; `AUTH_SERVICE_URL` defaults to `http://127.0.0.1:8001`).

The service is available at `http://localhost:8002`, its health check at `http://localhost:8002/health`, and interactive API documentation at `http://localhost:8002/docs`.

## Auth seam

Endpoints require an `Authorization: Bearer <token>` header whose access token is verified with authService (see `app/deps.py` and `docs/AUTH_INTEGRATION.md`). Requests without a valid token return 401; authenticated users without the `technical_support` role get 403 on mutations.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/equipment` | List equipment, optional `type` and `operational_status` filters (any authenticated user) |
| GET | `/equipment/{id}` | Fetch one item (404 if missing; any authenticated user) |
| POST | `/equipment` | Create item (`technical_support` only); creator comes from the verified token; seeds first history row |
| PATCH | `/equipment/{id}/quantity` | Update `total_owned_quantity` (must be >= 0; `technical_support` only) |
| GET | `/equipment/{id}/status` | Current status plus computed `available` flag (only `AVAILABLE` is in service; any authenticated user) |
| PATCH | `/equipment/{id}/status` | Atomic transition (`technical_support` only): body `{ "new_status": ..., "reason": ... }`; records who/when in history |
| GET | `/equipment/{id}/status/history` | Audit trail, newest first (any authenticated user) |

Valid statuses: `AVAILABLE`, `DAMAGED`, `UNDER_REPAIR`, `UNDER_MAINTENANCE`, `RETIRED`.

## Test

```powershell
ruff check .
pytest
```
