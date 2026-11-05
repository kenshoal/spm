-- Release 1 hotfix 23: a Coordinator can add a VIP when normal registration is full.
-- Run once, after 0070.
--
-- Q&A #99: "VIPs may be added manually even when normal registration is full, but the
-- overall event/venue capacity must still not be exceeded." coordinator_register_attendee
-- (0060) refused as soon as the places taken reached registration_capacity.
--
-- Now the manual path is refused only when the places taken reach BOTH the registration
-- capacity and the capacity of the event's venue(s): the sum of the maximum capacity of
-- each distinct venue with an approved booking for the event. An event with no approved
-- booking has no venue capacity to go above, so it behaves as before. Self-registration
-- and the waiting list still stop at registration_capacity. A registration over the
-- registration capacity still counts as a place taken, so a withdrawal does not open
-- a place for the public until the count is back under the capacity.

CREATE OR REPLACE FUNCTION private.event_venue_capacity(p_event_request_id uuid)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT sum(v.max_capacity)::integer
    FROM public.venues AS v
    WHERE v.id IN (
        SELECT b.venue_id FROM public.venue_booking_requests AS b
        WHERE b.event_request_id = p_event_request_id AND b.status = 'approved'
    );
$$;

REVOKE ALL ON FUNCTION private.event_venue_capacity(uuid)
    FROM PUBLIC, anon, authenticated, service_role;

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

    INSERT INTO public.event_registrations (event_request_id, attendee_id, registered_by)
    VALUES (p_event_request_id, v_attendee, p_coordinator_id::uuid)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;
