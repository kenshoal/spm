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
| `migrations/0001_baseline.sql` | `equipment` and `equipment_status_history` tables, status CHECK constraints, indexes |

`0001_baseline.sql` was derived from what `equipmentService` implies, then reconciled against the live database (columns, types, nullability, defaults, constraints, indexes) using the export queries below. Two things are deliberately absent:

- **No `operational_status` enum type** — the live DB stores status as `varchar` with CHECK constraints; the API mirrors the allowed values in `app/models.py`.
- **No `transition_equipment_status` function** — the live DB does not have it (verified 2026-09-19), so it is created by a later migration written to the router's RPC contract.

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
