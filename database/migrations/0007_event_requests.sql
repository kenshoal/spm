-- Reproducible event-request schema and organiser-only access rules.
-- The shared development project already matched this state on 2026-09-20.

CREATE TABLE IF NOT EXISTS public.event_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organiser_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'Draft'
        CHECK (status IN ('Draft', 'Submitted')),
    event_name text CHECK (char_length(event_name) <= 200),
    purpose text CHECK (char_length(purpose) <= 1000),
    description text CHECK (char_length(description) <= 5000),
    proposed_date_times timestamptz[] NOT NULL DEFAULT '{}',
    expected_attendance integer CHECK (expected_attendance > 0),
    venue_requirements text CHECK (char_length(venue_requirements) <= 2000),
    accessibility_needs text CHECK (char_length(accessibility_needs) <= 2000),
    equipment_requirements text CHECK (char_length(equipment_requirements) <= 2000),
    registration_needs text CHECK (char_length(registration_needs) <= 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.event_requests
    DROP COLUMN IF EXISTS temporary_organiser_id,
    ALTER COLUMN organiser_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS event_requests_organiser_status_idx
    ON public.event_requests (organiser_id, status);

CREATE OR REPLACE FUNCTION public.set_event_request_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_event_request_updated_at ON public.event_requests;
CREATE TRIGGER set_event_request_updated_at
    BEFORE UPDATE ON public.event_requests
    FOR EACH ROW
    EXECUTE FUNCTION public.set_event_request_updated_at();

ALTER TABLE public.event_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Organisers can create their drafts"
    ON public.event_requests;
CREATE POLICY "Organisers can create their drafts"
    ON public.event_requests
    FOR INSERT
    TO authenticated
    WITH CHECK (
        (SELECT auth.uid()) = organiser_id
        AND status = 'Draft'
        AND ((SELECT auth.jwt()) -> 'app_metadata' ->> 'role') = 'organiser'
    );

DROP POLICY IF EXISTS "Organisers can view their event requests"
    ON public.event_requests;
CREATE POLICY "Organisers can view their event requests"
    ON public.event_requests
    FOR SELECT
    TO authenticated
    USING (
        (SELECT auth.uid()) = organiser_id
        AND ((SELECT auth.jwt()) -> 'app_metadata' ->> 'role') = 'organiser'
    );

DROP POLICY IF EXISTS "Organisers can update their drafts"
    ON public.event_requests;
CREATE POLICY "Organisers can update their drafts"
    ON public.event_requests
    FOR UPDATE
    TO authenticated
    USING (
        (SELECT auth.uid()) = organiser_id
        AND status = 'Draft'
        AND ((SELECT auth.jwt()) -> 'app_metadata' ->> 'role') = 'organiser'
    )
    WITH CHECK (
        (SELECT auth.uid()) = organiser_id
        AND status = 'Draft'
        AND ((SELECT auth.jwt()) -> 'app_metadata' ->> 'role') = 'organiser'
    );

DROP POLICY IF EXISTS "Organisers can delete their drafts"
    ON public.event_requests;
CREATE POLICY "Organisers can delete their drafts"
    ON public.event_requests
    FOR DELETE
    TO authenticated
    USING (
        (SELECT auth.uid()) = organiser_id
        AND status = 'Draft'
        AND ((SELECT auth.jwt()) -> 'app_metadata' ->> 'role') = 'organiser'
    );

REVOKE ALL ON TABLE public.event_requests FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.event_requests TO authenticated;
GRANT ALL ON TABLE public.event_requests TO service_role;
