-- Hotfix 2 (H5): the "registration full" notice is decided in the transaction. Run once,
-- after 0088.
--
-- SCRUM-38 AC2: a newly saved registration can change the occupied places from below
-- capacity to full; the system decides this in one atomic step, with occupied meaning
-- Registered plus currently Offered places (the SCRUM-24 rule), and accepting an
-- already-held offer must not announce "full" again.
--
-- eventRequestService decided it after the commit and outside the lock, by counting
-- Registered rows only. Two registrations racing for the last places could both announce
-- "full" or neither could, and a pending offer was ignored.
--
-- Now the two functions that save a registration under the event lock record the answer
-- on the row they insert: event_registrations.filled_event is true only for the save that
-- took the event from below capacity to full. The service reads it from the returned row.
-- accept_waitlist_offer needs no change: an offer already held its place, so accepting
-- it leaves the occupied places as they were and filled_event stays false.
-- 0068 and 0082 are not edited: both functions are replaced here.

ALTER TABLE public.event_registrations
    ADD COLUMN IF NOT EXISTS filled_event boolean NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION public.register_for_event(
    p_event_request_id uuid,
    p_attendee_id uuid,
    p_now timestamptz
)
RETURNS public.event_registrations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_taken integer;
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

    -- D6: taken = Registered + Offered, so a pending offer is not a free place.
    v_taken := private.places_taken(p_event_request_id);

    IF v_taken >= v_event.registration_capacity THEN
        RAISE EXCEPTION 'event full' USING ERRCODE = 'P0004';
    END IF;

    -- SCRUM-38 AC2: decided here, under the event lock, from the same count that just
    -- allowed the save (Registered plus Offered). True only for the save that takes the
    -- event from below capacity to full.
    INSERT INTO public.event_registrations (event_request_id, attendee_id, filled_event)
    VALUES (p_event_request_id, p_attendee_id,
            v_taken + 1 >= v_event.registration_capacity)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

CREATE OR REPLACE FUNCTION public.coordinator_register_attendee(
    p_event_request_id uuid,
    p_coordinator_id text,
    p_attendee_email text
)
RETURNS public.event_registrations
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_attendee uuid;
    v_taken integer;
    v_venue_capacity integer;
    v_row public.event_registrations;
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND OR v_event.status <> 'Confirmed' OR p_coordinator_id IS DISTINCT FROM (
        SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
        WHERE a.event_request_id = p_event_request_id ORDER BY a.id DESC LIMIT 1
    ) THEN
        RAISE EXCEPTION 'event not found' USING ERRCODE = 'P0002';
    END IF;

    -- Effective roles in authService's precedence (as in 0038): staff_roles rows,
    -- then app_metadata.roles, then app_metadata.role, else attendee.
    SELECT u.id INTO v_attendee
    FROM auth.users AS u
    WHERE lower(u.email) = lower(btrim(p_attendee_email))
      AND 'attendee' = ANY (
        CASE
            WHEN EXISTS (SELECT 1 FROM public.staff_roles AS r WHERE r.user_id = u.id)
                THEN ARRAY(SELECT r.role::text FROM public.staff_roles AS r WHERE r.user_id = u.id)
            WHEN jsonb_typeof(u.raw_app_meta_data -> 'roles') = 'array'
                AND jsonb_array_length(u.raw_app_meta_data -> 'roles') > 0
                THEN ARRAY(SELECT jsonb_array_elements_text(u.raw_app_meta_data -> 'roles'))
            WHEN jsonb_typeof(u.raw_app_meta_data -> 'role') = 'string'
                AND u.raw_app_meta_data ->> 'role' <> ''
                THEN ARRAY[u.raw_app_meta_data ->> 'role']
            ELSE ARRAY['attendee']
        END
      );
    IF v_attendee IS NULL THEN
        RAISE EXCEPTION 'attendee not found' USING ERRCODE = 'P0002';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.event_registrations
        WHERE event_request_id = p_event_request_id
          AND attendee_id = v_attendee
          AND status = 'Registered'
    ) THEN
        RAISE EXCEPTION 'already registered' USING ERRCODE = 'P0004';
    END IF;

    IF v_event.registration_capacity IS NULL THEN
        RAISE EXCEPTION 'capacity not set' USING ERRCODE = 'P0004';
    END IF;

    -- D6: the manual path respects a pending offer like every other check.
    v_taken := private.places_taken(p_event_request_id);
    v_venue_capacity := private.event_venue_capacity(p_event_request_id);

    IF v_taken >= v_event.registration_capacity
       AND v_taken >= COALESCE(v_venue_capacity, 0) THEN
        RAISE EXCEPTION 'event full' USING ERRCODE = 'P0004';
    END IF;

    -- SCRUM-38 AC2: only the save that takes the event from below capacity to full counts.
    -- A VIP added to an event that is already full does not announce "full" again.
    INSERT INTO public.event_registrations (event_request_id, attendee_id, registered_by, filled_event)
    VALUES (p_event_request_id, v_attendee, p_coordinator_id::uuid,
            v_taken < v_event.registration_capacity AND v_taken + 1 >= v_event.registration_capacity)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.register_for_event(uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_for_event(uuid, uuid, timestamptz)
    TO service_role;

REVOKE EXECUTE ON FUNCTION public.coordinator_register_attendee(uuid, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.coordinator_register_attendee(uuid, text, text)
    TO service_role;
