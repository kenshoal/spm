-- SCRUM-24 hotfix: restore the waiting-list hand-over in withdraw_registration.
-- Safe to re-run. Needs 0067 and 0068. Run after 0093.
--
-- 0067 (SCRUM-25) and 0068 (SCRUM-24) both replace withdraw_registration; 0068's
-- version keeps 0067's 'already checked in' refusal and adds the hand-over
-- (private.open_place after the UPDATE, AC2-H1). Applied in file order that is
-- what runs. On shared development 0067 was applied after the waiting list, so
-- 0067's version won: a withdrawal freed the place but offered it to nobody,
-- and the Coordinator's choice found no open place.
-- This re-creates 0068's function unchanged, so the result no longer depends on
-- the order the two were applied in. Verify with
-- verify_withdrawal_waitlist_handover.sql.
--
-- A withdrawal made while the hand-over was missing left its place unoffered.
-- This migration does not re-offer those places; reset the affected test events.

CREATE OR REPLACE FUNCTION public.withdraw_registration(
    p_registration_id uuid,
    p_attendee_id uuid,
    p_now timestamptz
)
RETURNS public.event_registrations
LANGUAGE plpgsql
SECURITY DEFINER
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

    -- SCRUM-25 (0067): a checked-in attendee can't withdraw. Kept here because
    -- this replaces 0067's version of the function.
    IF v_row.attended_at IS NOT NULL THEN
        RAISE EXCEPTION 'already checked in' USING ERRCODE = 'P0004';
    END IF;

    SELECT min(d) INTO v_start FROM unnest(v_event.proposed_date_times) AS d;

    IF v_event.status <> 'Confirmed' OR v_start IS NULL OR p_now >= v_start THEN
        RAISE EXCEPTION 'withdrawal not permitted' USING ERRCODE = 'P0004';
    END IF;

    UPDATE public.event_registrations
    SET status = 'Withdrawn', withdrawn_at = p_now
    WHERE id = p_registration_id
    RETURNING * INTO v_row;

    -- SCRUM-24: the place is now free, so promote in this same transaction
    -- (AC2-H1). The call sits after the UPDATE, when the place is actually free.
    PERFORM private.open_place(v_event_id, p_now);

    RETURN v_row;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.withdraw_registration(uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.withdraw_registration(uuid, uuid, timestamptz)
    TO service_role;
