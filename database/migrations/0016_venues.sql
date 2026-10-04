-- Reproducible venue-catalogue schema (SCRUM-30 / SCRUM-9).
-- The shared development project already matched this state on 2026-09-28:
-- the table and enums were created in the SQL Editor, and this migration
-- records them so a fresh project can be rebuilt. Safe to re-run.

DO $$
BEGIN
    CREATE TYPE public.room_layout AS ENUM
        ('classroom', 'theatre', 'boardroom', 'banquet', 'exhibition');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END;
$$;

-- Shared with venue_blocks.slots.
DO $$
BEGIN
    CREATE TYPE public.booking_slot AS ENUM ('AM', 'PM', 'NIGHT');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END;
$$;

DO $$
BEGIN
    CREATE TYPE public.venue_status AS ENUM ('available', 'blocked');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END;
$$;

CREATE TABLE IF NOT EXISTS public.venues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    location text NOT NULL,
    max_capacity integer NOT NULL,
    facilities text[] NOT NULL,
    accessibility_features text[] NOT NULL,
    supported_layouts public.room_layout[] NOT NULL,
    operating_slots public.booking_slot[] NOT NULL,
    status public.venue_status NOT NULL DEFAULT 'available',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- venueService is the only client and uses the server-side secret key, which
-- bypasses RLS. Browser roles get no direct access.
ALTER TABLE public.venues ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.venues FROM anon, authenticated;
