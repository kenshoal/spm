-- Safety Review status and Safety Officer role (SCRUM-60 increment 1). Safe to re-run.
--
-- Adds 'Safety Review' between Planning and Confirmed and the safety_officer
-- staff role. SCRUM-58 AC2 moves Planning -> Safety Review; SCRUM-60's decision
-- function (a later migration) is the only way to Confirmed. The coordinator
-- function below is 0026 with one change: Safety Review is cancellable. It still
-- cannot reach Confirmed.

ALTER TABLE public.event_requests
    DROP CONSTRAINT IF EXISTS event_requests_status_check;
ALTER TABLE public.event_requests
    ADD CONSTRAINT event_requests_status_check CHECK (status IN (
        'Draft', 'Submitted', 'Under Review', 'Changes Requested', 'Approved',
        'Planning', 'Safety Review', 'Confirmed', 'Completed', 'Cancelled', 'Rejected'
    ));

ALTER TABLE public.staff_roles
    DROP CONSTRAINT IF EXISTS staff_roles_role_check;
ALTER TABLE public.staff_roles
    ADD CONSTRAINT staff_roles_role_check CHECK (role IN (
        'admin', 'attendee', 'event_coordinator', 'event_operations_manager',
        'event_organiser', 'safety_officer', 'technical_support', 'venue_staff'
    ));

CREATE OR REPLACE FUNCTION public.advance_event_request_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_to_status varchar
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_current public.event_requests;
    v_latest_coordinator varchar;
BEGIN
    SELECT * INTO v_current
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_latest_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;

    IF v_latest_coordinator IS NULL OR v_latest_coordinator <> p_coordinator_id THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    IF NOT (
        (p_to_status = 'Under Review' AND v_current.status = 'Submitted')
        OR (p_to_status = 'Planning' AND v_current.status = 'Approved')
        OR (p_to_status = 'Completed' AND v_current.status = 'Confirmed')
        OR (
            p_to_status = 'Cancelled'
            AND v_current.status IN (
                'Submitted', 'Under Review', 'Changes Requested',
                'Approved', 'Planning', 'Safety Review', 'Confirmed'
            )
        )
    ) THEN
        RAISE EXCEPTION 'transition not allowed from status %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.' || CASE p_to_status
            WHEN 'Under Review' THEN 'review' WHEN 'Planning' THEN 'planning'
            WHEN 'Completed' THEN 'completion' ELSE 'cancellation' END);
    UPDATE public.event_requests
    SET status = p_to_status
    WHERE id = p_event_request_id
      AND status = v_current.status
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.advance_event_request_by_coordinator(
    uuid, varchar, varchar
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.advance_event_request_by_coordinator(
    uuid, varchar, varchar
) TO service_role;
