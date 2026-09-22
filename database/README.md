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
