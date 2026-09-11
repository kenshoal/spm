# authService

Initial FastAPI authentication microservice scaffold.

## Run locally

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The service is available at `http://localhost:8000`, its health check at `http://localhost:8000/health`, and interactive API documentation at `http://localhost:8000/docs`.

## Current authentication features

- `POST /users` registers a user and returns public profile data.
- Passwords are hashed with Argon2 before storage.
- Email addresses are unique without regard to letter casing.

User storage is intentionally in memory for this increment and resets whenever the service restarts.

## Test

```powershell
ruff check .
pytest
```
