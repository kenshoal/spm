-- Withdraw a registration (SCRUM-22). Safe to re-run. Needs 0048.
--
-- Widens event_registrations.status to Registered / Withdrawn and adds
-- withdrawn_at, kept in step with status by a CHECK. A withdrawal is a soft
-- update, so the row stays as history. Capacity and the one-active-registration
-- index both look at status = 'Registered' only, so a withdrawn row frees its
-- place and lets the attendee register again with no change to
-- register_for_event.
--
-- withdraw_registration locks the EVENT row first (the same lock
-- register_for_event takes) and then the registration row, so a withdrawal and
-- a registration for the freed place queue instead of racing. Allowed while the
-- event is Confirmed and p_now is before its earliest proposed date (SCRUM-22
-- D1); the cut-off is read from the locked row, so an approved date change
-- applies at once. Server-only, like register_for_event.

ALTER TABLE public.event_registrations
    ADD COLUMN IF NOT EXISTS withdrawn_at timestamptz;

ALTER TABLE public.event_registrations
    DROP CONSTRAINT IF EXISTS event_registrations_status_check;
ALTER TABLE public.event_registrations
    ADD CONSTRAINT event_registrations_status_check
    CHECK (status IN ('Registered', 'Withdrawn'));

ALTER TABLE public.event_registrations
    DROP CONSTRAINT IF EXISTS event_registrations_withdrawn_at_check;
ALTER TABLE public.event_registrations
    ADD CONSTRAINT event_registrations_withdrawn_at_check
    CHECK ((status = 'Withdrawn') = (withdrawn_at IS NOT NULL));

GRANT UPDATE (status, withdrawn_at) ON public.event_registrations TO service_role;

CREATE OR REPLACE FUNCTION public.withdraw_registration(
    p_registration_id uuid,
    p_attendee_id uuid,
    p_now timestamptz
)
RETURNS public.event_registrations
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event_id uuid;
    v_event public.event_requests;
    v_row public.event_registrations;
    v_start timestamptz;
BEGIN
    -- event_request_id never changes, so it is safe to read before locking.
    SELECT event_request_id INTO v_event_id
    FROM public.event_registrations
    WHERE id = p_registration_id AND attendee_id = p_attendee_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'registration not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = v_event_id
    FOR UPDATE;

    SELECT * INTO v_row
    FROM public.event_registrations
    WHERE id = p_registration_id
    FOR UPDATE;

    IF v_row.status = 'Withdrawn' THEN
        RAISE EXCEPTION 'already withdrawn' USING ERRCODE = 'P0004';
    END IF;

    SELECT min(d) INTO v_start FROM unnest(v_event.proposed_date_times) AS d;

    IF v_event.status <> 'Confirmed' OR v_start IS NULL OR p_now >= v_start THEN
        RAISE EXCEPTION 'withdrawal not permitted' USING ERRCODE = 'P0004';
    END IF;

    -- SCRUM-24 hook: promote the first waitlisted attendee here, in this
    -- transaction, once the waiting list exists.
    UPDATE public.event_registrations
    SET status = 'Withdrawn', withdrawn_at = p_now
    WHERE id = p_registration_id
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.withdraw_registration(uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.withdraw_registration(uuid, uuid, timestamptz)
    TO service_role;
