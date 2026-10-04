# equipmentService

Equipment catalogue & status microservice (SCRUM-16, SCRUM-45). Reads/writes the `equipment` table in Supabase. Every mutation is a single atomic Postgres function call: creation also seeds the first `equipment_status_history` row, quantity changes append to `equipment_quantity_history` under a row lock, and status transitions go through `transition_equipment_status`.

## Run locally

The standard project workflow is to run `docker compose up --build -d` from
the repository root. This exposes equipmentService on `http://localhost:8002`.
Use the commands below only when developing this service by itself.

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

## Database & RPCs

Mutations are Postgres functions (RPCs) in the shared database, defined in [`database/migrations/`](../../database/migrations/) — apply new files in filename order via the Supabase SQL Editor (see [`database/README.md`](../../database/README.md)):

| Function | Behaviour |
| --- | --- |
| `create_equipment` | Inserts the equipment row and its first `equipment_status_history` entry (`old_status` NULL) in one transaction; returns the row |
| `update_equipment_quantity` | Locks the row (`FOR UPDATE`), appends old/new quantities to `equipment_quantity_history`, updates the row; returns it |
| `transition_equipment_status` | Locks the row, updates `operational_status`, appends to `equipment_status_history` |

All three raise with ERRCODE `P0002` when the equipment id is unknown; the service maps that code to `404 Equipment not found` (`app/rpc_errors.py`) rather than matching error-message text. Any other RPC failure maps to `500`.

Note: `transition_equipment_status` did not exist in the live database until migration `0002` — `PATCH /equipment/{id}/status` fails with `500` until it is applied.

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
