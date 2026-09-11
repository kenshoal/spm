# eventRequestService

FastAPI service for creating and managing an Event Organiser's event-request
drafts. SQLite is used for the first persistent CRUD increment.

## Current API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/event-requests` | Create a Draft |
| `GET` | `/event-requests` | List the current organiser's requests |
| `GET` | `/event-requests/{id}` | Retrieve one request |
| `PATCH` | `/event-requests/{id}` | Update a Draft |
| `DELETE` | `/event-requests/{id}` | Delete a Draft |
| `GET` | `/health` | Service health check |

Until `authService` exposes an authentication contract, every event-request
operation requires an `X-Organiser-Id` header. This is a temporary local
identity boundary and must be replaced by verified authentication data.

## Run locally on macOS/Linux

Python 3.11 or newer is required.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8002
```

The API is available at `http://localhost:8002`, with interactive documentation
at `http://localhost:8002/docs`.

The database defaults to `db.sqlite3` in this service directory. Override its
location with the `EVENT_REQUEST_DB_PATH` environment variable.

## Test

```bash
ruff check .
pytest
```

