-- Attendee registration for Confirmed events (SCRUM-21). Safe to re-run.
--
-- Adds the registration window and capacity to event_requests (read-only here:
-- the screen that sets them is a separate story), the event_registrations table,
-- and register_for_event, which locks the event row and checks status, window,
-- duplicate and capacity before inserting. Two attendees racing for the last place
-- queue on the lock, so exactly one succeeds. Server-only: browser roles can
-- neither call the function nor read the table.

ALTER TABLE public.event_requests
    ADD COLUMN IF NOT EXISTS registration_opens_at timestamptz,
    ADD COLUMN IF NOT EXISTS registration_closes_at timestamptz,
    ADD COLUMN IF NOT EXISTS registration_capacity integer;

ALTER TABLE public.event_requests
    DROP CONSTRAINT IF EXISTS event_requests_registration_window_check;
ALTER TABLE public.event_requests
    ADD CONSTRAINT event_requests_registration_window_check
    CHECK (registration_closes_at > registration_opens_at);

ALTER TABLE public.event_requests
    DROP CONSTRAINT IF EXISTS event_requests_registration_capacity_check;
ALTER TABLE public.event_requests
    ADD CONSTRAINT event_requests_registration_capacity_check
    CHECK (registration_capacity > 0);

CREATE TABLE IF NOT EXISTS public.event_registrations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL
        REFERENCES public.event_requests (id) ON DELETE CASCADE,
    attendee_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    -- SCRUM-22 widens this CHECK for Withdrawn.
    status text NOT NULL DEFAULT 'Registered' CHECK (status IN ('Registered')),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- One active registration per attendee per event (SCRUM-21 D5).
CREATE UNIQUE INDEX IF NOT EXISTS event_registrations_one_active_idx
    ON public.event_registrations (event_request_id, attendee_id)
    WHERE status = 'Registered';
CREATE INDEX IF NOT EXISTS event_registrations_attendee_created_idx
    ON public.event_registrations (attendee_id, created_at);

ALTER TABLE public.event_registrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.event_registrations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON public.event_registrations TO service_role;

CREATE OR REPLACE FUNCTION public.register_for_event(
    p_event_request_id uuid,
    p_attendee_id uuid,
    p_now timestamptz
)
RETURNS public.event_registrations
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_registered integer;
    v_row public.event_registrations;
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND OR v_event.status <> 'Confirmed' THEN
        RAISE EXCEPTION 'event not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_event.registration_opens_at IS NULL
        OR v_event.registration_closes_at IS NULL
        OR v_event.registration_capacity IS NULL
        OR p_now < v_event.registration_opens_at
        OR p_now >= v_event.registration_closes_at THEN
        RAISE EXCEPTION 'registration not open' USING ERRCODE = 'P0004';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.event_registrations
        WHERE event_request_id = p_event_request_id
          AND attendee_id = p_attendee_id
          AND status = 'Registered'
    ) THEN
        RAISE EXCEPTION 'already registered' USING ERRCODE = 'P0004';
    END IF;

    SELECT count(*) INTO v_registered
    FROM public.event_registrations
    WHERE event_request_id = p_event_request_id AND status = 'Registered';

    IF v_registered >= v_event.registration_capacity THEN
        RAISE EXCEPTION 'event full' USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO public.event_registrations (event_request_id, attendee_id)
    VALUES (p_event_request_id, p_attendee_id)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.register_for_event(uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_for_event(uuid, uuid, timestamptz)
    TO service_role;
