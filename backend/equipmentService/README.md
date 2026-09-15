# equipmentService

Equipment catalogue microservice (SCRUM-45). Reads/writes the `equipment` table in Supabase and seeds the first `equipment_status_history` row on create.

## Run locally

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8002
```

Requires `SUPABASE_URL` and `SUPABASE_SECRET_KEY` in the environment (or a `.env` file in the working directory).

The service is available at `http://localhost:8002`, its health check at `http://localhost:8002/health`, and interactive API documentation at `http://localhost:8002/docs`.

## Auth seam

Endpoints require an `X-User-Id` header (stubbed auth — see `app/deps.py` and `docs/AUTH_INTEGRATION.md`). Requests without it return 401.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/equipment` | List equipment, optional `type` and `operational_status` filters |
| GET | `/equipment/{id}` | Fetch one item (404 if missing) |
| POST | `/equipment` | Create item; creator comes from `X-User-Id`; seeds first history row |
| PATCH | `/equipment/{id}/quantity` | Update `total_owned_quantity` (must be >= 0) |

## Test

```powershell
ruff check .
pytest
```
