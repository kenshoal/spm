-- Release 1 hotfix 4: the Coordinator sets the registration period and capacity.
-- Run once, after 0068.
--
-- Q&A #30 puts the Coordinator in charge of the registration start and end dates,
-- and #42 and #127 allow the period to be extended or reopened. 0048 added the
-- columns, but nothing but test scripts could write them, so no one could register.
--
-- set_event_registration_settings locks the event row (the same lock as registering,
-- so a capacity change cannot race the last place), rechecks the latest assignment,
-- and refuses a capacity below the places already taken (Registered plus Offered).
-- Raising capacity offers each new place to the waiting list in FIFO order.

CREATE OR REPLACE FUNCTION public.set_event_registration_settings(
    p_event_request_id uuid,
    p_coordinator_id text,
    p_opens_at timestamptz,
    p_closes_at timestamptz,
    p_capacity integer,
    p_now timestamptz
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_coordinator text;
    v_taken integer;
    v_new_places integer;
BEGIN
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC LIMIT 1;
    IF p_coordinator_id IS NULL OR v_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    IF v_event.status NOT IN ('Approved', 'Planning', 'Safety Review', 'Confirmed') THEN
        RAISE EXCEPTION 'registration settings not allowed from status %', v_event.status
            USING ERRCODE = 'P0004';
    END IF;

    IF p_opens_at IS NULL OR p_closes_at IS NULL OR p_capacity IS NULL
       OR p_closes_at <= p_opens_at OR p_capacity <= 0 THEN
        RAISE EXCEPTION 'invalid registration settings' USING ERRCODE = '22023';
    END IF;

    v_taken := private.places_taken(p_event_request_id);
    IF p_capacity < v_taken THEN
        RAISE EXCEPTION 'capacity below places taken' USING ERRCODE = 'P0004';
    END IF;

    v_new_places := CASE
        WHEN v_event.registration_capacity IS NULL THEN 0
        ELSE GREATEST(p_capacity - GREATEST(v_event.registration_capacity, v_taken), 0)
    END;

    UPDATE public.event_requests
    SET registration_opens_at = p_opens_at,
        registration_closes_at = p_closes_at,
        registration_capacity = p_capacity
    WHERE id = p_event_request_id
    RETURNING * INTO v_event;

    FOR i IN 1..v_new_places LOOP
        PERFORM private.open_place(p_event_request_id, p_now);
    END LOOP;

    RETURN v_event;
END;
$$;

REVOKE ALL ON FUNCTION public.set_event_registration_settings(uuid, text, timestamptz, timestamptz, integer, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_event_registration_settings(uuid, text, timestamptz, timestamptz, integer, timestamptz)
    TO service_role;
