-- Baseline schema for the shared Supabase database: equipment domain.
--
-- NOTE: this state already exists in the live database — that is exactly
-- what this file was reconciled against. Do NOT re-run it against the live
-- DB (the plain CREATE TABLE statements will error). It serves as a
-- reference snapshot and for fresh environments only.
--
-- Reconciled against the live database on 2026-09-19 using the export
-- queries in database/README.md (columns, types, nullability, defaults,
-- constraints, and indexes all verified). Status values are enforced by
-- CHECK constraints, not a Postgres enum; the five valid values mirror
-- equipmentService's app/models.py.

CREATE TABLE equipment (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type varchar(120) NOT NULL,
    description text,
    total_owned_quantity integer NOT NULL CHECK (total_owned_quantity >= 0),
    home_location varchar(120) NOT NULL,
    operational_status varchar(20) NOT NULL DEFAULT 'AVAILABLE'
        CHECK (operational_status IN ('AVAILABLE', 'DAMAGED', 'UNDER_REPAIR', 'UNDER_MAINTENANCE', 'RETIRED')),
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_equipment_type ON equipment (type);
CREATE INDEX idx_equipment_status ON equipment (operational_status);

CREATE TABLE equipment_status_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    equipment_id uuid NOT NULL REFERENCES equipment (id) ON DELETE CASCADE,
    old_status varchar(20),
    new_status varchar(20) NOT NULL
        CHECK (new_status IN ('AVAILABLE', 'DAMAGED', 'UNDER_REPAIR', 'UNDER_MAINTENANCE', 'RETIRED')),
    reason varchar(255),
    changed_by uuid NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_esh_equipment ON equipment_status_history (equipment_id, changed_at DESC);

-- transition_equipment_status deliberately not created here: it does not
-- exist in the live database (verified 2026-09-19) and is added by a later
-- migration, written to the router's RPC contract.

-- TODO(paste-from-supabase): RLS policies and triggers, if any exist --
-- not yet exported. The service-role key bypasses RLS either way, so this
-- does not affect service behaviour.
