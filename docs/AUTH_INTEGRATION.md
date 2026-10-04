# Auth Integration Contract

Backend services verify callers with authService and enforce role-based authorisation.

## The Bearer contract

- Callers send `Authorization: Bearer <supabase-access-token>` (the token issued by `POST /auth/login`).
- Missing or malformed headers return `401 Authentication required`.
- The service calls authService `GET /auth/me` with the token; authService verifies it against Supabase and returns `{id, email, role, roles}`.
- authService `401` → `401 Invalid session`; any other non-2xx or network failure → `502 Authentication service unavailable`; an unusable payload → `502`.
- Identity is resolved server-side only — no caller-supplied ID is trusted. `changed_by` (status transitions) and `created_by` (equipment creation) are derived from the verified `id`.

On top of it, role checks return `403 Insufficient permissions` unless at least one assigned role is allowed.

## Role model

Roles are read per request from the `staff_roles` table, with Supabase `app_metadata.role(s)` as a migration fallback (never `user_metadata`, which users can self-edit). A user without a stored role is treated as `attendee`. Role changes take effect immediately — no new token is needed.

| Role | Meaning |
| --- | --- |
| `attendee` | Default for every authenticated user |
| `event_organiser` | Event-request operations |
| `event_coordinator` | Event coordination |
| `event_operations_manager` | Assign Event Coordinators |
| `technical_support` | Equipment mutations (SCRUM-16/SCRUM-45 actors) |
| `admin` | Role assignment via the authService admin endpoint |
| `venue_staff` | Venue catalogue mutations |

## Endpoint requirements

| Service | Route | Requirement |
| --- | --- | --- |
| equipmentService | `POST /equipment` | `technical_support` |
| equipmentService | `PATCH /equipment/{id}/quantity` | `technical_support` |
| equipmentService | `PATCH /equipment/{id}/status` | `technical_support` |
| equipmentService | `GET /equipment`, `GET /equipment/{id}` | any authenticated user |
| equipmentService | `GET /equipment/{id}/status`, `GET /equipment/{id}/status/history` | any authenticated user |
| eventRequestService | Draft CRUD under `/event-requests` | `event_organiser` |
| eventRequestService | `POST /event-requests/{id}/coordinator` | `event_operations_manager` |
| eventRequestService | `GET /event-requests/assigned-to-me` | `event_coordinator`; results are limited to requests where the caller is the latest assigned Coordinator |
| eventRequestService | `GET /event-requests/{id}` | owning `event_organiser` or currently assigned `event_coordinator`; unrelated eligible users receive `404` |
| eventRequestService | `POST /event-requests/{id}/review` | `event_coordinator` and current assignment |
| eventRequestService | `POST /event-requests/{id}/cancellation` | currently assigned `event_coordinator`; allowed only from a non-terminal, non-Draft status |
| eventRequestService | `POST /event-requests/{id}/completion` | currently assigned `event_coordinator`; allowed only from `Confirmed` |
| eventRequestService | `GET /event-requests/{id}/coordinator` | owning `event_organiser`, `event_operations_manager`, or currently assigned `event_coordinator` |
| venueService | `POST /venues`, `PATCH /venues/{id}` | `venue_staff` |
| venueService | venue reads and search | any authenticated user |

This covers SCRUM-45's "viewed by an authorised user" acceptance criterion: reads need any authenticated user; mutations need `technical_support`.

## Role assignment

Two ways to assign roles:

1. **Bootstrap (one-off)**: add the initial admin role to `staff_roles` using the Supabase SQL Editor.
2. **Ongoing**: `PATCH /auth/users/{user_id}/role` on authService with an admin's Bearer token and body `{"role": ...}`. An Event Operations Manager may assign only `event_coordinator`. The endpoint requires `SUPABASE_SECRET_KEY` and returns `503` when unset, `404` for unknown users, and `403` for disallowed assignments.

Target `user_id` values come from that user's `/auth/me` response (or the Supabase dashboard user list).

## Where users come from

Supabase Auth owns the user records. The `created_by` / `changed_by` UUIDs stored in Supabase are Supabase Auth user UUIDs; there is deliberately **no cross-service foreign key** — referential integrity of users is Supabase Auth's responsibility.

## Why no local JWT verification (yet)

Role is not in the JWT claims without Supabase's custom access-token hook. Calling `/auth/me` is the sanctioned "verification endpoint" option from the original contract; if per-request latency ever matters, local signature verification (JWKS or a shared public key) plus the custom access-token hook is the upgrade path.
