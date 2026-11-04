-- SCRUM-24 hotfix: joining the waiting list closes at the cut-off. Safe to re-run.
-- Needs 0068. Run after 0092.
--
-- The timer closes every Waiting entry once p_now >= start - 72h (AC10, D11),
-- but join_waitlist only checked the registration window. Where registration
-- runs past the cut-off (an event starting within 3 days, or already under way)
-- a join was accepted and closed seconds later with a waitlist_closed notice.
-- This replaces join_waitlist from 0068 (not edited) with one more refusal,
-- 'waitlist closed' (P0004), checked after the registration window; everything
-- else is unchanged. An event with no date has no cut-off, as in the timer.
-- Verify with verify_waitlist_join_cutoff.sql.

CREATE OR REPLACE FUNCTION public.join_waitlist(
    p_event_request_id uuid,
    p_attendee_id uuid,
    p_now timestamptz
)
RETURNS public.event_waitlist_entries
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_row public.event_waitlist_entries;
    v_start timestamptz;
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

    -- Hotfix: the list closes at the cut-off, start - 72h (AC10), so a join from
    -- that instant is refused rather than accepted and closed on the next timer pass.
    SELECT min(d) INTO v_start FROM unnest(v_event.proposed_date_times) AS d;
    IF v_start IS NOT NULL AND p_now >= v_start - interval '72 hours' THEN
        RAISE EXCEPTION 'waitlist closed' USING ERRCODE = 'P0004';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.event_registrations
        WHERE event_request_id = p_event_request_id
          AND attendee_id = p_attendee_id
          AND status = 'Registered'
    ) THEN
        RAISE EXCEPTION 'already registered' USING ERRCODE = 'P0004';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.event_waitlist_entries
        WHERE event_request_id = p_event_request_id
          AND attendee_id = p_attendee_id
          AND status IN ('Waiting', 'Offered')
    ) THEN
        RAISE EXCEPTION 'already waitlisted' USING ERRCODE = 'P0004';
    END IF;

    IF private.places_taken(p_event_request_id) < v_event.registration_capacity THEN
        RAISE EXCEPTION 'places available' USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO public.event_waitlist_entries
        (event_request_id, attendee_id, status, queued_at)
    VALUES (p_event_request_id, p_attendee_id, 'Waiting', p_now)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.join_waitlist(uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.join_waitlist(uuid, uuid, timestamptz)
    TO service_role;
