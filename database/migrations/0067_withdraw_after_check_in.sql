-- A checked-in attendee can't withdraw (SCRUM-25, review of PR #103). Safe to re-run.
-- Needs 0061 (attended_at) and 0062 (withdraw_registration).
--
-- Check-in opens at 00:00 SGT on the event day and withdrawal closes at the
-- start time, so both are open for a few hours. Without this, a withdrawal
-- after check-in leaves a Withdrawn row with attended_at set and frees a place
-- during the event. Replaces withdraw_registration from 0062 (not edited) with
-- one more refusal, 'already checked in', read from the locked row; everything
-- else is unchanged.

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

    IF v_row.attended_at IS NOT NULL THEN
        RAISE EXCEPTION 'already checked in' USING ERRCODE = 'P0004';
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
