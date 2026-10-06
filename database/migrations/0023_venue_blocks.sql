-- Reproducible venue-block schema (SCRUM-23).
-- The shared development project already has this table: it was created in the
-- SQL Editor, and this migration records it so a fresh project can be rebuilt.
-- Columns, types, defaults and the venues foreign key match the shared table's
-- Data API description on 2026-10-06. Safe to re-run.
--
-- Rules the service enforces (VenueBlockCreate): end_date is on or after
-- start_date; slots has at least one value and no duplicates; NIGHT belongs to
-- its starting date. created_by comes from the verified Venue Staff token.
-- created_by is nullable here because the shared table allows it; historical
-- rows may lack a creator.
--
-- Creating a block and approving a booking request (SCRUM-15) must both lock
-- the venues row, so neither can bypass the other's checks. That lock belongs
-- in those write paths, not in this table.

-- booking_slot is created in 0016_venues.sql.

DO $$
BEGIN
    CREATE TYPE public.block_reason AS ENUM
        ('maintenance', 'renovation', 'safety', 'internal_use');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END;
$$;

-- lifted means explicitly withdrawn, not merely a period in the past.
DO $$
BEGIN
    CREATE TYPE public.block_status AS ENUM ('active', 'lifted');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END;
$$;

CREATE TABLE IF NOT EXISTS public.venue_blocks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id uuid NOT NULL REFERENCES public.venues (id),
    start_date date NOT NULL,
    end_date date NOT NULL,
    slots public.booking_slot[] NOT NULL,
    reason_category public.block_reason NOT NULL,
    reason_detail text,
    status public.block_status NOT NULL DEFAULT 'active',
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Blocks for one venue, used by search, availability and the calendar.
CREATE INDEX IF NOT EXISTS venue_blocks_venue_idx
    ON public.venue_blocks (venue_id);

-- venueService is the only client and uses the server-side secret key, which
-- bypasses RLS. Browser roles get no direct access: block reasons are internal.
ALTER TABLE public.venue_blocks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.venue_blocks FROM anon, authenticated;
