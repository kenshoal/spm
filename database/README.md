# Database

All backend services share one Supabase (Postgres) database, so the schema lives here — above any single service — as plain SQL migrations applied in filename order.

## Applying a migration

Migrations are applied manually through the Supabase dashboard (there is no CLI/`psql` access from CI):

1. Supabase dashboard → **SQL Editor** → **New query**.
2. Paste the full contents of the next unapplied file from `migrations/` (filename order: `0001`, `0002`, …).
3. **Run**, and repeat until every file is applied.

Apply each file exactly once and never edit a file that has already been applied — new changes go in a new file.

## Migrations

| File | Purpose |
| --- | --- |
| `migrations/0001_baseline.sql` | `equipment` and `equipment_status_history` tables, status CHECK constraints, indexes. **Reference snapshot / fresh environments only** — this state already exists in the live DB; do not re-run it there |
| `migrations/0002_transition_equipment_status.sql` | `transition_equipment_status` RPC: atomic status change + history row; ERRCODE `P0002` for unknown ids |
| `migrations/0003_create_equipment_fn.sql` | `create_equipment` RPC: atomic insert of the equipment row + first history entry |
| `migrations/0004_quantity_history.sql` | `equipment_quantity_history` audit table + `update_equipment_quantity` RPC (row lock, ERRCODE `P0002`) |
| `migrations/0005_rls_and_function_access.sql` | RLS enabled on the three equipment tables (default-deny for anon/authenticated). Its function revokes were a no-op — see 0006 |
| `migrations/0006_rpc_execute_grants.sql` | RPC `EXECUTE` revoked from `PUBLIC` (which anon/authenticated inherit through) and granted explicitly to `service_role` |
| `migrations/0007_event_requests.sql` | Event-request table, validation constraints, update timestamp trigger and organiser-only RLS policies. The shared development project already matched this schema on 20 September 2026 |
| `migrations/0008_event_request_submission_outbox.sql` | Private transactional outbox and triggers that record one `event_request.submitted` event for a direct submission or Draft-to-Submitted transition |
| `migrations/0009_event_request_outbox_organiser_index.sql` | Covering index for the outbox organiser foreign key and future notification-recipient lookups |
| `migrations/0010_staff_roles.sql` | `staff_roles` role-assignment table keyed by `(user_id, role)`, RLS enabled, service-role access only |
| `migrations/0011_event_coordinator_assignments.sql` | `event_coordinator_assignments` append-only table backing Coordinator assignment and the awaiting-assignment queue. **Reference snapshot / fresh environments only** — this table was created by hand in the dashboard and already exists live; do not re-run it there |
| `migrations/0011_event_request_review_status.sql` | Full event-request status constraint and server-only access to coordinator assignment history; API services enforce actor and transition rules |
| `migrations/0012_coordinator_status_transitions.sql` | `advance_event_request_by_coordinator` RPC (SCRUM-28): locks the request row, re-checks the latest coordinator assignment and applies one coordinator transition atomically. ERRCODE `P0002` not found, `P0003` not the assigned coordinator, `P0004` transition not allowed. Revokes `EXECUTE` from `PUBLIC` only — see 0013 |
| `migrations/0013_coordinator_transition_execute_grants.sql` | Revokes the direct `EXECUTE` grants Supabase's default privileges give `anon` and `authenticated` on the 0012 function, leaving `service_role` only (same fix as 0005 + 0006 for the equipment RPCs) |
| `migrations/0014_atomic_coordinator_assignment.sql` | `assign_event_request_coordinator` RPC: locks the event request, validates its state and the target coordinator role, then inserts assignment history atomically. Server role only |
| `migrations/0015_harden_coordinator_transition_search_path.sql` | Pins the SCRUM-28 transition RPC to an empty search path, clearing the Supabase mutable-search-path warning without changing behavior |
| `migrations/0016_event_request_review_decisions.sql` | SCRUM-17 review history plus server-only atomic RPCs for decisions, organiser clarification responses and resuming review |
| `migrations/0017_notifications.sql` | `notifications` table for SCRUM-37: one row per recipient per event, unique `(recipient_id, event_id)` so a retried event is stored once, newest-first inbox index, RLS on with service-role access only |
| `migrations/0018_venue_booking_requests.sql` | `venue_booking_requests` table for SCRUM-32: dates, slots and status with CHECK constraints (slot rules as in `venue_blocks`, decision fields always consistent with the status), a restrictive foreign key to `venues`, four lookup indexes, RLS on with service-role access only. Applied to shared development on 4 October 2026 |
| `migrations/0019_client_organisations.sql` | SCRUM-39: `client_organisations`, `organisation_members` (one organisation per Organiser) and `event_requests.organisation_id`, stamped from the Organiser's membership on insert and never changed afterwards. RLS on, service-role access only. Verify with `verify_client_organisations.sql`. Applied to the shared development project on 5 October 2026 |
| `migrations/0020_equipment_reservations.sql` | `equipment_reservations` table for SCRUM-10: units of an equipment row committed to an event, `quantity > 0` and `return_date >= collection_date` CHECKs, FKs to `equipment` and `event_requests`, hold-window index, RLS on with service-role access only. Starts empty; SCRUM-13 writes rows. Applied to the shared development project on 6 October 2026, replacing the placeholder table from `feat/scoped-resource-access` (SCRUM-39), which was dropped the same day once the two stories deconflicted — SCRUM-10's hold-ledger schema (`collection_date`/`return_date`) is the canonical one |
| `migrations/0023_venue_blocks.sql` | `venue_blocks` table for SCRUM-23 with its `block_reason` and `block_status` enums, a foreign key to `venues` and a per-venue index. **Reference snapshot** of the table created by hand in the dashboard (safe to re-run: it skips existing objects), plus RLS on and `REVOKE ALL` from `anon` and `authenticated`, so only venueService's secret key can read block reasons. Applied to shared development on 6 October 2026 through the SQL Editor; afterwards `has_table_privilege` returns false for `anon` and `authenticated`, and the publishable key gets `401` (`42501`) while venueService still reads both existing blocks |

Verify `0020` after applying it: run
[`verify_equipment_reservations.sql`](verify_equipment_reservations.sql) in the
SQL Editor — it exercises the CHECK constraints and both foreign keys
(including the refusal paths) and prints
`ALL EQUIPMENT RESERVATION VERIFICATIONS PASSED` on success, rolling back so
no data is left behind.

`0011` was applied to the shared Supabase development project via MCP on 22
September 2026. Do not apply it again there; retain the file for fresh
environments and schema review.

`0012` was applied to the shared Supabase development project on 23 September
2026 (the corrected version, with the fixed P0004 `RAISE`). Do not apply it
again there. Fresh environments must apply it before running the SCRUM-28
eventRequestService, otherwise `/review`, `/cancellation` and `/completion`
return 502.

`0013` was applied to the shared development project on 23 September 2026,
after which `verify_event_request_status_transitions.sql` passed there. Do not
apply either file again there.

`0014` was applied to the shared development project on 24 September 2026 and
`verify_atomic_coordinator_assignment.sql` completed there without error. Do
not apply it again there; retain it for fresh environments.

`0015` was applied to shared development on 24 September 2026. The full status
transition verification passed afterward, and the Supabase security advisor no
longer reports `advance_event_request_by_coordinator` as having a mutable search
path.

`0017` was applied to shared development via the Supabase MCP on 29 September
2026. Do not apply it again there (it is safe to re-run, but there is no need).
Read-only checks afterwards confirmed RLS on, all five constraints and both
indexes present, no `anon`/`authenticated` access, and `service_role` insert and
update. `verify_notifications.sql` was run against a local Postgres, not shared
development, because it writes rows (they are rolled back).

`0018` was applied to shared development on 4 October 2026 through the SQL Editor,
and `verify_venue_booking_requests.sql` then ran there without error (it rolls
back every row it writes). Read-only Data API checks afterwards found the table
readable by the service role and refused to the browser role. Do not apply it
again there (it is safe to re-run, but there is no need).

New RPCs should revoke `EXECUTE` from `PUBLIC, anon, authenticated` in the same
migration that creates them. Supabase grants all three by default.

`0001_baseline.sql` was derived from what `equipmentService` implies, then reconciled against the live database (columns, types, nullability, defaults, constraints, indexes) using the export queries below. One thing is deliberately absent:

- **No `operational_status` enum type** — the live DB stores status as `varchar` with CHECK constraints; the API mirrors the allowed values in `app/models.py`.

Note: `transition_equipment_status` did **not** exist in the live database (verified 2026-09-19) even though `PATCH /equipment/{id}/status` calls it — `0002` creates it from the router's RPC contract.

## Verifying the SQL functions

The service's pytest suite fakes the database, so the functions' real behaviour (atomicity, `P0002` contract, audit logging, the quantity CHECK) is verified by [verify_equipment_functions.sql](verify_equipment_functions.sql). Run it in the SQL Editor after applying the migrations: it exercises every function including failure paths, prints `ALL EQUIPMENT FUNCTION VERIFICATIONS PASSED` on success, and `ROLLBACK`s — leaving no data behind. RLS behaviour is verified separately with the publishable key over the REST API (see `docs/`).

The event-request submission outbox is verified by
[`verify_event_request_submission_outbox.sql`](verify_event_request_submission_outbox.sql).
It proves that a Draft creates no event, each supported submission path creates
exactly one event, and a repeated status write does not create a duplicate. The
script rolls back all test rows.

The notifications table is verified by
[`verify_notifications.sql`](verify_notifications.sql). Run it after `0017`:
it proves a retried event is stored once, one event can notify several
recipients, a non-object payload is refused and browser roles cannot read the
table. The script rolls back all test rows.

The booking-request table is verified by
[`verify_venue_booking_requests.sql`](verify_venue_booking_requests.sql).
Run it once before `0018`, when it should stop with a missing-table error (the
Red result), and again after, when it should print
`ALL VENUE BOOKING REQUEST VERIFICATIONS PASSED`. It covers dates, slots,
required columns, status and decision consistency, the venue foreign key and
server-only access. The script rolls back all rows and needs no Supabase Auth
user.

The coordinator transition function is verified by
[`verify_event_request_status_transitions.sql`](verify_event_request_status_transitions.sql).
Run it after `0012` and `0013`: it exercises Submitted → Under Review, non-terminal →
Cancelled and Confirmed → Completed, every `P0002`/`P0003`/`P0004` failure
path (including reassignment away and repeated actions), confirms refused calls
leave the status unchanged, and checks the `EXECUTE` grants. It prints
`ALL EVENT-REQUEST STATUS TRANSITION VERIFICATIONS PASSED` and rolls back.
Requires at least one Supabase Auth user (used as the organiser).

Atomic assignment is verified by
[`verify_atomic_coordinator_assignment.sql`](verify_atomic_coordinator_assignment.sql).
After `0014`, it exercises missing, Draft, terminal and wrong-role failures,
successful assignment and reassignment history, the shared row-lock contract
and server-only execution grants. It rolls back all verification data.

SCRUM-17 review decisions are verified by
[`verify_event_request_review_decisions.sql`](verify_event_request_review_decisions.sql).
After `0016`, it exercises every review outcome, reason and response retention, refused
side effects and server-only permissions. It rolls back all verification data.

## Test accounts

[`seed_test_accounts.sql`](seed_test_accounts.sql) confirms the shared dev test
accounts (one per role, two coordinators, password `12345678`) and assigns
their roles. Register the accounts first; see "Test accounts" in
`docs/authentication.txt`. Dev only; never run it on production.

## Verification queries

Re-run these in the SQL Editor if you suspect the migration file has drifted from the live schema:

```sql
-- Columns: types, nullability, defaults
SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;

-- Varchar lengths and identity columns
SELECT table_name, column_name, character_maximum_length, is_identity, identity_generation
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (data_type = 'character varying' OR is_identity = 'YES');

-- Constraints: PK / FK / CHECK
SELECT conrelid::regclass AS table_name, conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace;

-- Indexes on the equipment tables
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('equipment', 'equipment_status_history');

-- Functions defined for the equipment domain
SELECT proname, pg_get_functiondef(oid) FROM pg_proc
WHERE proname ILIKE '%transition%' OR proname ILIKE '%equipment%';
```

Still to export from the live database (open TODO in `0001_baseline.sql`): RLS policies (`SELECT * FROM pg_policies WHERE schemaname = 'public';`) and triggers (`SELECT * FROM information_schema.triggers WHERE trigger_schema = 'public';`).
