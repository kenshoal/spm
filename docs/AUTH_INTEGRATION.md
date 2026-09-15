# Auth Integration Contract (authService → equipment services)

What the future authService implementer needs to wire real authentication into `equipmentService` (SCRUM-45) and `equipmentStatusService` (SCRUM-16) **without touching any equipment endpoint handlers**.

## Current seam (stub)

Both equipment services expose a FastAPI dependency `get_current_user` in `app/deps.py`:

- Today it trusts the `X-User-Id` request header, returning `User(id=<header value>, role="technical_support")`.
- A missing header returns `401`.
- The role is stubbed; every caller is treated as `technical_support`.
- `changed_by` (status transitions) and `created_by` (equipment creation) are derived server-side from `user.id` — clients never send them in a body.

Endpoints using the dependency today:

| Service | Route | Intended requirement (once roles are real) |
| --- | --- | --- |
| equipmentService | `POST /equipment` | `technical_support` |
| equipmentService | `PATCH /equipment/{id}/quantity` | `technical_support` |
| equipmentStatusService | `PATCH /equipment/{id}/status` | `technical_support` |
| equipmentService | `GET /equipment`, `GET /equipment/{id}` | any authenticated user |
| equipmentStatusService | `GET /equipment/{id}/status`, `GET /equipment/{id}/status/history` | any authenticated user |

This table covers SCRUM-45's "viewed by an authorised user" acceptance criterion: read-only views need any authenticated user; mutations need `technical_support`.

## What authService must deliver

1. **Login endpoint** that issues a signed JWT.
2. **Token contract (claims):**
   - `sub` — the user's UUID (this is what authService owns in its users table)
   - `role` — e.g. `technical_support`
3. **A way for other services to verify the token**: either a published verification key (JWKS endpoint or shared public key) or a verification endpoint. Signed-token verification local to each service is preferred — no network call per request.

## The swap

In each equipment service, replace only the body of `get_current_user` in `app/deps.py`:

- Read the `Authorization: Bearer <token>` header instead of `X-User-Id`.
- Verify signature + expiry.
- Extract `sub` and `role` claims.
- Return `User(id=<sub>, role=<role>)`.

Optionally add a `require_role(...)` dependency layered on top for the mutation routes listed above. No handler code changes are required — handlers already receive `user` via `Depends(get_current_user)`.

## Caller contract changes

- Clients stop sending `X-User-Id` and send `Authorization: Bearer <token>` instead.
- `changed_by` / creator continue to be derived server-side from `sub` — no request-body changes.

## Where users come from

authService owns the users table. The `created_by` / `changed_by` UUIDs stored in Supabase are authService user UUIDs; there is deliberately **no cross-service foreign key** — referential integrity of users is authService's responsibility.
