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

Requires `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `AUTH_SERVICE_URL` in the environment (or a `.env` file in the working directory; `AUTH_SERVICE_URL` defaults to `http://127.0.0.1:8001`). `VENUE_SERVICE_URL` (default `http://127.0.0.1:8004`) is needed for `POST /equipment/availability-check` (SCRUM-10). `EVENT_REQUEST_SERVICE_URL` (default `http://127.0.0.1:8003`) is needed for the equipment-requirements endpoints (SCRUM-33).

The service is available at `http://localhost:8002`, its health check at `http://localhost:8002/health`, and interactive API documentation at `http://localhost:8002/docs`.

## Auth seam

Endpoints require an `Authorization: Bearer <token>` header whose access token is verified with authService (see `app/deps.py` and `docs/AUTH_INTEGRATION.md`). Requests without a valid token return 401. Reads require `event_coordinator` or `technical_support`; mutations require `technical_support`.

## Database & RPCs

Mutations are Postgres functions (RPCs) in the shared database, defined in [`database/migrations/`](../../database/migrations/) — apply new files in filename order via the Supabase SQL Editor (see [`database/README.md`](../../database/README.md)):

| Function | Behaviour |
| --- | --- |
| `create_equipment` | Inserts the equipment row and its first `equipment_status_history` entry (`old_status` NULL) in one transaction; returns the row |
| `update_equipment_quantity` | Locks the row (`FOR UPDATE`), appends old/new quantities to `equipment_quantity_history`, updates the row; returns it |
| `transition_equipment_status` | Locks the row, updates `operational_status`, appends to `equipment_status_history` |
| `transition_equipment_requirement` | Locks the `equipment_requirements` row, refuses a stale expected status, applies one allowed arrangement transition (`requested → in_progress/arranged`, `in_progress ↔ arranged`, `in_progress → in_progress` only with a non-blank note) and records who/when. `P0002` unknown id, `P0004` disallowed/stale/blank-note update |
| `reserve_equipment` | Locks the `equipment_requirements` row, then the `equipment` row (SCRUM-13 D6a), re-checks the row's status, the requirement's outstanding quantity and the units held on the busiest day of `[p_collection_date, p_return_date]`, then inserts with `event_request_id` copied from the requirement. `P0002` unknown requirement/equipment, `P0004` refused under the lock |

The first three raise with ERRCODE `P0002` when the equipment id is unknown; the service maps that code to `404 Equipment not found` (`app/rpc_errors.py`) rather than matching error-message text. The requirement function maps `P0002` to `404 Equipment requirement not found` and `P0004` to `409 Transition not allowed`. `reserve_equipment` maps `P0002` to `404 Equipment or requirement not found` (only reachable in a race with a delete) and `P0004` to `409 Equipment no longer available`. Any other RPC failure maps to `500`.

Note: `transition_equipment_status` did not exist in the live database until migration `0002` — `PATCH /equipment/{id}/status` fails with `500` until it is applied.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/equipment` | List equipment, optional `type` and `operational_status` filters |
| GET | `/equipment/{id}` | Fetch one item (404 if missing) |
| POST | `/equipment` | Create item (`technical_support` only); creator comes from the verified token; seeds first history row |
| PATCH | `/equipment/{id}/quantity` | Update `total_owned_quantity` (must be >= 0; `technical_support` only) |
| GET | `/equipment/{id}/status` | Current status plus computed `available` flag (only `AVAILABLE` is in service). `available` means working; `available_quantity` is `total_owned_quantity` minus the units reserved today (Singapore time, SCRUM-10), so fully reserved stock shows `available: true, available_quantity: 0` |
| PATCH | `/equipment/{id}/status` | Atomic transition (`technical_support` only): body `{ "new_status": ..., "reason": ... }`; records who/when in history |
| GET | `/equipment/{id}/status/history` | Audit trail, newest first |
| POST | `/equipment/availability-check` | Check how many units of each requested type could be committed to an event (SCRUM-10; `technical_support` only, read-only — nothing is booked). Body: `{ "start_date": "2026-10-14", "end_date": "2026-10-14", "venue_id": "v-big", "items": [{ "type": "Projector", "quantity": 5 }] }`. Response `200`: one `{ "requested", "available", "shortfall" }` entry per requested type, keyed by the type string as sent — a shortfall is still `200`, never `409`. Excludes non-`AVAILABLE` rows, units reserved on the busiest overlapping day of the hold (`start_date − 1` plus one transfer day when the row's building differs from the venue's), and honours the D-1 → Return Day hold. Calls venueService `GET /venues/locations` with the caller's token (SCRUM-13 D11). Errors: `422` invalid body, `401`/`403` no session/role, `404` unknown venue, `502` venueService unreachable or refusing, `500` database failure. Needs migration `0019` (`equipment_reservations`) applied |

Valid statuses: `AVAILABLE`, `DAMAGED`, `UNDER_REPAIR`, `UNDER_MAINTENANCE`, `RETIRED`.

### Equipment requirements (SCRUM-33)

An assigned Event Coordinator records what equipment an event needs; Technical Support reviews and arranges. equipmentService owns the `equipment_requirements` table but not event relationships: to decide "does the caller currently coordinate this event", it asks eventRequestService with the caller's own token — `GET /event-requests/{id}/coordinator` compared with the caller's id, plus, on record only, `GET /event-requests/{id}` for the status and the name/date-time snapshot stored on the row. Technical Support is role-wide and never calls eventRequestService.

| Method | Path | Description |
| --- | --- | --- |
| POST | `/equipment-requirements` | Record one requirement (`event_coordinator` assigned to the event only). Body: `{ "event_request_id", "equipment_type", "quantity", "technical_requirements?" }`; extra fields forbidden. The type is matched against non-retired catalogue rows ignoring case and extra spaces and stored in the catalogue's spelling; quantity is a whole number 1..2147483647; technical requirements are optional, at most 2,000 characters (blank stored as NULL). `201` with the stored row (`status: requested`, event snapshot, `recorded_by` from the token). Errors: `422` invalid body or unknown type, `404` not the assigned Coordinator (indistinguishable from a missing event), `409` event Cancelled/Completed/Rejected, `401`/`403` no session/role, `502` eventRequestService unavailable, `500` database failure. Needs migration `0021` |
| GET | `/equipment-requirements` | Technical Support's review queue: every event's requirements with one status (default `requested`, `?status=` to choose), oldest first |
| GET | `/equipment-requirements/by-event/{event_request_id}` | One event's requirements, oldest first (assigned `event_coordinator`, or any `technical_support` or `safety_officer`) |
| GET | `/equipment-requirements/{id}` | One requirement, every field (same readers; an unassigned Coordinator gets the same 404 as a missing requirement) |
| PATCH | `/equipment-requirements/{id}/arrangement` | `technical_support` only. Body: `{ "expected_status", "status", "support_note?" }`. The database function applies the transition under a row lock and refuses disallowed or stale updates (`409`); a blank or omitted note keeps the existing note. `404` unknown id, `422` invalid body |

### Equipment reservations (SCRUM-13)

Technical Support reserves units of one catalogue row against a recorded equipment requirement, so the same units are never committed to two overlapping holds. The row offers `total_owned_quantity` minus the units already committed on its busiest day inside its own hold window (`start_date − 1`, one more day when the row's building differs from the venue's); a requirement may not be over-reserved. Reserving does not change the requirement's arrangement status (SCRUM-33's `PATCH …/arrangement` does that). Needs migration `0027` (`requirement_id` and `reserve_equipment`) — until it is applied, the POST returns `500`.

| Method | Path | Description |
| --- | --- | --- |
| POST | `/equipment-reservations` | Reserve units of one row against one requirement (`technical_support` only). Body: `{ "requirement_id", "equipment_id", "quantity", "start_date", "end_date", "venue_id" }`; extra fields forbidden — the event comes from the requirement and the creator from the token. Check order: `404` "Equipment requirement not found" / "Equipment not found", `422` "Equipment type does not match the requirement", `409` "Equipment not available", `409` "Exceeds the equipment requirement", `404` "Venue not found", `409` shortfall `detail` `{ "message": "Insufficient equipment available", "requested": Q, "available": A, "shortfall": Q − A }` — then `reserve_equipment` re-checks under the lock (`409` "Equipment no longer available"). `201` with the stored row: `id`, `requirement_id`, `event_request_id`, `equipment_id`, `quantity`, `collection_date` (hold start), `return_date` (event end), `created_by`, `created_at`. Calls venueService `GET /venues/locations` with the caller's token (D11). Also `401`/`403` no session/role, `422` invalid body, `502` venueService unreachable or refusing, `500` database failure |
| GET | `/equipment-reservations/by-event/{event_request_id}` | One event's reservations, oldest first (`created_at`, then `id`; `technical_support` or `safety_officer`, read-only). `200` with the stored rows, `[]` when the event has none. Also `422` malformed id, `401`/`403`, `500` database failure |

## Test

```powershell
ruff check .
pytest
```

`tests/test_venue_contract.py` (marker `cross_service`) starts the real venueService from `../venueService` in a subprocess with in-memory storage, plus a fake authService, and checks the reservation and availability-check endpoints against venueService's real role check. It needs no network or database and runs in plain `pytest` and CI; skip it offline with `pytest -m "not cross_service"`.
