-- SCRUM-25: the event's coordinator checks a registered attendee in on an event day.
-- Attendance is attended_at/checked_in_by on the registration; status stays 'Registered',
-- so capacity counts are unchanged. The function locks the event, then the registration,
-- rechecks assignment, status, event day (Asia/Singapore dates of proposed_date_times),
-- the registration and whether it is already checked in, then updates; a refusal writes nothing.
-- Requires 0011 coordinator assignments and 0048 registrations.
ALTER TABLE public.event_registrations
    ADD COLUMN IF NOT EXISTS attended_at timestamptz,
    ADD COLUMN IF NOT EXISTS checked_in_by uuid;

CREATE OR REPLACE FUNCTION public.check_in_attendee(
    p_event_request_id uuid,
    p_registration_id uuid,
    p_coordinator_id text,
    p_now timestamptz
)
RETURNS public.event_registrations
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
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

    IF NOT EXISTS (
        SELECT 1 FROM unnest(v_event.proposed_date_times) AS d
        WHERE (d AT TIME ZONE 'Asia/Singapore')::date = (p_now AT TIME ZONE 'Asia/Singapore')::date
    ) THEN
        RAISE EXCEPTION 'not event day' USING ERRCODE = 'P0004';
    END IF;

    SELECT * INTO v_row
    FROM public.event_registrations
    WHERE id = p_registration_id
      AND event_request_id = p_event_request_id
      AND status = 'Registered'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'registration not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_row.attended_at IS NOT NULL THEN
        RAISE EXCEPTION 'already checked in' USING ERRCODE = 'P0004';
    END IF;

    UPDATE public.event_registrations
    SET attended_at = p_now, checked_in_by = p_coordinator_id::uuid
    WHERE id = p_registration_id
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.check_in_attendee(uuid, uuid, text, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_in_attendee(uuid, uuid, text, timestamptz)
    TO service_role;
-- SECURITY INVOKER as service_role: it needs UPDATE, which 0048 did not grant.
GRANT UPDATE (attended_at, checked_in_by) ON public.event_registrations TO service_role;
