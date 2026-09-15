# authService

FastAPI authentication microservice scaffold backed by Supabase Auth.

## Run locally

```powershell
uv sync --extra dev --locked
Copy-Item .env.example .env
uv run uvicorn app.main:app --reload
```

The service is available at `http://localhost:8000`, its health check at `http://localhost:8000/health`, and interactive API documentation at `http://localhost:8000/docs`.

Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` in `.env` using the values from your Supabase project settings. Never place a Supabase secret or service-role key in client-facing configuration.

## Current authentication setup

- The official Supabase Python SDK is configured from environment variables.
- Supabase Auth will own credentials, password handling, sessions, and JWT issuance.
- `POST /auth/register` creates an email/password user through Supabase Auth.
- Registration returns whether email confirmation is required, but does not expose session tokens.

The previous in-memory user store and local password hashing have been removed to avoid maintaining a second authentication source.

## Test

```powershell
ruff check .
pytest
```
