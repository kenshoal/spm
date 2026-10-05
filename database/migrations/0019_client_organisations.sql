-- SCRUM-39: client organisations and Event Organiser membership.
-- Organisers in one client organisation may view each other's non-Draft
-- requests (clarification #81). Records are seeded; maintaining them is E3-4.

CREATE TABLE IF NOT EXISTS public.client_organisations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 200),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- One organisation per Organiser (Team Design Proposal, card E3-4).
CREATE TABLE IF NOT EXISTS public.organisation_members (
    user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    organisation_id uuid NOT NULL
        REFERENCES public.client_organisations (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS organisation_members_organisation_idx
    ON public.organisation_members (organisation_id);

ALTER TABLE public.event_requests
    ADD COLUMN IF NOT EXISTS organisation_id uuid
        REFERENCES public.client_organisations (id);

-- Serves the "shared with my organisation" list (non-Draft, newest first).
CREATE INDEX IF NOT EXISTS event_requests_organisation_created_idx
    ON public.event_requests (organisation_id, created_at DESC)
    WHERE organisation_id IS NOT NULL AND status <> 'Draft';

ALTER TABLE public.client_organisations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organisation_members ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.client_organisations FROM anon, authenticated;
REVOKE ALL ON public.organisation_members FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.client_organisations TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.organisation_members TO service_role;

-- A request records its Organiser's organisation when created and keeps it:
-- a supplied value is ignored on insert and any change is reverted on update.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION private.stamp_event_request_organisation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT m.organisation_id INTO NEW.organisation_id
        FROM public.organisation_members AS m
        WHERE m.user_id = NEW.organiser_id;
    ELSE
        NEW.organisation_id := OLD.organisation_id;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.stamp_event_request_organisation()
    FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS stamp_event_request_organisation ON public.event_requests;
CREATE TRIGGER stamp_event_request_organisation
    BEFORE INSERT OR UPDATE OF organisation_id ON public.event_requests
    FOR EACH ROW
    EXECUTE FUNCTION private.stamp_event_request_organisation();
