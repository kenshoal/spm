-- SCRUM-41: a coordinator registers an existing attendee account on a Confirmed event.
-- registered_by records who entered it (null = self-registered). The function locks the
-- event row and rechecks assignment, status, attendee, duplicate and capacity, then inserts;
-- a refusal writes nothing. No registration-window check (approved 23 Oct 2026).
-- Requires 0010 staff_roles, 0011 coordinator assignments and 0048 registrations.
ALTER TABLE public.event_registrations ADD COLUMN IF NOT EXISTS registered_by uuid;

-- SECURITY DEFINER: it resolves the attendee from auth.users by email.
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
    v_registered integer;
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

    SELECT count(*) INTO v_registered
    FROM public.event_registrations
    WHERE event_request_id = p_event_request_id AND status = 'Registered';

    IF v_registered >= v_event.registration_capacity THEN
        RAISE EXCEPTION 'event full' USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO public.event_registrations (event_request_id, attendee_id, registered_by)
    VALUES (p_event_request_id, v_attendee, p_coordinator_id::uuid)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.coordinator_register_attendee(uuid, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.coordinator_register_attendee(uuid, text, text)
    TO service_role;
