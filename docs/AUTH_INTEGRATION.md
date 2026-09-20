# Auth Integration Contract (authService → equipment services)

Implemented: `equipmentService` (SCRUM-16, SCRUM-45) verifies every caller with authService and enforces role-based authorisation. The stub that trusted the `X-User-Id` header is gone.

## The Bearer contract

The equipment service exposes a FastAPI dependency `get_current_user` in `app/deps.py`:

- Callers send `Authorization: Bearer <supabase-access-token>` (the token issued by `POST /auth/login`).
- Missing or malformed headers return `401 Authentication required`.
- The service calls authService `GET /auth/me` with the token; authService verifies it against Supabase and returns `{id, email, role}`.
- authService `401` → `401 Invalid session`; any other non-2xx or network failure → `502 Authentication service unavailable`; an unusable payload → `502`.
- Identity is resolved server-side only — no caller-supplied ID is trusted. `changed_by` (status transitions) and `created_by` (equipment creation) are derived from the verified `id`.

On top of it, `require_role(*allowed)` returns `403 Insufficient permissions` for callers whose role is not allowed.

## Role model

Roles are read per request from Supabase **`app_metadata.role`** (never `user_metadata`, which users can self-edit). A user without a stored role is treated as `event_coordinator`. Role changes take effect immediately — no new token is needed.

| Role | Meaning |
| --- | --- |
| `event_coordinator` | Default for every authenticated user; read access |
| `technical_support` | Equipment mutations (SCRUM-16/SCRUM-45 actors) |
| `admin` | Role assignment via the authService admin endpoint |
| `venue_staff` | Reserved (matches the venueService stub) |

## Endpoint requirements

| Service | Route | Requirement |
| --- | --- | --- |
| equipmentService | `POST /equipment` | `technical_support` |
| equipmentService | `PATCH /equipment/{id}/quantity` | `technical_support` |
| equipmentService | `PATCH /equipment/{id}/status` | `technical_support` |
| equipmentService | `GET /equipment`, `GET /equipment/{id}` | any authenticated user |
| equipmentService | `GET /equipment/{id}/status`, `GET /equipment/{id}/status/history` | any authenticated user |

This covers SCRUM-45's "viewed by an authorised user" acceptance criterion: reads need any authenticated user; mutations need `technical_support`.

## Role assignment

Two ways to set `app_metadata.role`:

1. **Bootstrap (one-off)**: Supabase dashboard → Authentication → Users → user → *Edit* → **Raw App Meta Data** JSON, e.g. `{"role": "admin"}` for one lead account, `{"role": "technical_support"}` for staff.
2. **Ongoing**: `PATCH /auth/users/{user_id}/role` on authService with an admin's Bearer token and body `{"role": ...}`. Requires authService to have `SUPABASE_SECRET_KEY` configured (server-side only); returns `503` when unset, `404` for unknown users, `403` for non-admin callers.

Target `user_id` values come from that user's `/auth/me` response (or the Supabase dashboard user list).

## Where users come from

Supabase Auth owns the user records. The `created_by` / `changed_by` UUIDs stored in Supabase are Supabase Auth user UUIDs; there is deliberately **no cross-service foreign key** — referential integrity of users is Supabase Auth's responsibility.

## Why no local JWT verification (yet)

Role is not in the JWT claims without Supabase's custom access-token hook. Calling `/auth/me` is the sanctioned "verification endpoint" option from the original contract; if per-request latency ever matters, local signature verification (JWKS or a shared public key) plus the custom access-token hook is the upgrade path.
