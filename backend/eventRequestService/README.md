# eventRequestService

FastAPI service for creating and managing an Event Organiser's event-request
drafts. Drafts are persisted in the shared Supabase project.

## Current API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/event-requests` | Create a Draft |
| `POST` | `/event-requests/submissions` | Submit a complete new request |
| `GET` | `/event-requests` | List the current organiser's requests |
| `GET` | `/event-requests/{id}` | Retrieve one request |
| `PATCH` | `/event-requests/{id}` | Update a Draft |
| `POST` | `/event-requests/{id}/submit` | Submit a completed Draft |
| `DELETE` | `/event-requests/{id}` | Delete a Draft |
| `GET` | `/event-requests/awaiting-assignment` | List Submitted requests with no Coordinator |
| `POST` | `/event-requests/{id}/coordinator` | Assign or reassign a Coordinator |
| `GET` | `/event-requests/{id}/coordinator` | Get the current Coordinator |
| `POST` | `/event-requests/{id}/review` | Assigned Coordinator starts review (`Submitted` → `Under Review`) |
| `GET` | `/health` | Service health check |

Every event-request operation requires `Authorization: Bearer <access-token>`.
Draft CRUD requires `event_organiser`, coordinator assignment and the
awaiting-assignment queue require `event_operations_manager`, and starting
review requires `event_coordinator`.
The service asks authService to verify that token with Supabase, then scopes
drafts to the returned user ID. A current assignment may be read by the owning
Event Organiser, an Event Operations Manager, or the currently assigned Event
Coordinator. Multi-role users are authorised when any assigned role and the
required request relationship match. The browser cannot choose the organiser ID.
The non-null `organiser_id` column stores that verified UUID. This service no
longer reads or writes `temporary_organiser_id`; the deployed Supabase table
must match that contract before authenticated requests are tested.

Draft fields may remain incomplete. Submission requires every currently defined
event-request field, changes the status to `Submitted`, and makes the request
read-only. Requirements that do not apply must still contain explicit text such
as `None`.

The database migration `0011_event_request_review_status.sql` permits the full
agreed status vocabulary. This increment implements only Draft → Submitted and
Submitted → Under Review; the remaining SCRUM-28 transition commands are still
to be added.

## Run locally on macOS/Linux

The standard project workflow is to run `docker compose up --build -d` from
the repository root. This exposes eventRequestService on
`http://localhost:8003`. Use the commands below only when developing this
service by itself.

Python 3.11 or newer is required.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
# Replace SUPABASE_SECRET_KEY with the server-only key from Supabase.
# Run authService on port 8001, or set AUTH_SERVICE_URL to its internal URL.
uvicorn app.main:app --reload --port 8003
```

The API is available at `http://localhost:8003`, with interactive documentation
at `http://localhost:8003/docs`.

`SUPABASE_SECRET_KEY` must remain in the backend environment. Do not put it in
frontend variables or commit it to source control. New `sb_secret_...` keys are
preferred; the legacy service-role key is also supported during migration.

## Test

```bash
ruff check .
pytest
```
