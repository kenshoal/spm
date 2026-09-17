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
| `GET` | `/health` | Service health check |

Every event-request operation requires `Authorization: Bearer <access-token>`.
The service asks authService to verify that token with Supabase, then scopes
drafts to the returned user ID. The browser cannot choose the organiser ID.
The `organiser_id` column stores that verified ID. Existing databases must be
migrated from `temporary_organiser_id` to `organiser_id` before using this
service with authenticated requests. Drafts saved under the old column remain
available after the migration when their values are preserved.

Draft fields may remain incomplete. Submission requires every currently defined
event-request field, changes the status to `Submitted`, and makes the request
read-only. Requirements that do not apply must still contain explicit text such
as `None`.

## Run locally on macOS/Linux

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
