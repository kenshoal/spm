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

Optionally set `SUPABASE_SECRET_KEY` (service-role key) to enable role assignment. It is used server-side only, never in client-facing configuration.

## Current authentication setup

- The official Supabase Python SDK is configured from environment variables.
- Supabase Auth will own credentials, password handling, sessions, and JWT issuance.
- `POST /auth/register` creates an email/password user through Supabase Auth.
- Registration returns whether email confirmation is required, but does not expose session tokens.
- `POST /auth/login` signs in a confirmed user and returns Supabase access and refresh tokens. Send credentials only over HTTPS and store refresh tokens securely.
- `GET /auth/me` verifies a `Bearer` access token with Supabase and returns the authenticated user ID and role; missing or invalid tokens receive 401.
- Roles are read per request from Supabase `app_metadata.role` (never `user_metadata`, which users can self-edit). Without a stored role the caller is treated as `event_coordinator`.
- `PATCH /auth/users/{user_id}/role` assigns a role (`admin`, `organiser`, `technical_support`, `event_coordinator`, `venue_staff`). The caller must be authenticated with the `admin` role (403 otherwise); requires `SUPABASE_SECRET_KEY` (503 if unset). authService reads the new role immediately. A client that accesses Supabase directly must refresh its JWT before role-based RLS sees the change.

The previous in-memory user store and local password hashing have been removed to avoid maintaining a second authentication source.

## Test

```powershell
ruff check .
pytest
```
