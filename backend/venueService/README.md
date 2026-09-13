# venueService

FastAPI microservice for the venue catalogue and venue search / filtering.

## Scope

| Capability | Endpoints |
| --- | --- |
| Maintain the venue catalogue | `POST /venues`, `GET /venues/{id}`, `PATCH /venues/{id}`, `GET /venues` |
| Search and filter venues | `GET /venues/search` |

Storage is an in-memory repository (`app/repository.py`) — a scaffold to be
replaced with a persistent backend once the project's database infrastructure
lands. Authorisation dependencies in `app/dependencies.py` are stubs pending
integration with `authService`.

`GET /venues/search` accepts a `date` parameter but does not yet evaluate
per-date availability; a venue is excluded only when its whole-venue `status`
is not `available`. Per-date-slot blocking belongs to the venue availability
calendar / venue-blocking stories.

## Run locally

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
