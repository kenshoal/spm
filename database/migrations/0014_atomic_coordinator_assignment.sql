-- Serialize coordinator assignment with coordinator-driven status transitions.
--
-- Both functions lock the same event_requests row. A reassignment and a status
-- transition for one request therefore cannot make authorization decisions
-- from different assignment snapshots.
CREATE FUNCTION public.assign_event_request_coordinator(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_assigned_by varchar
)
RETURNS public.event_coordinator_assignments
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_status text;
    v_assignment public.event_coordinator_assignments;
BEGIN
    SELECT status INTO v_status
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_status = 'Draft' OR v_status IN ('Completed', 'Cancelled', 'Rejected') THEN
        RAISE EXCEPTION 'coordinator assignment not allowed from status %', v_status
            USING ERRCODE = 'P0004';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.staff_roles
        WHERE user_id::text = p_coordinator_id
          AND role = 'event_coordinator'
    ) THEN
        RAISE EXCEPTION 'selected user is not an event coordinator'
            USING ERRCODE = 'P0005';
    END IF;

    INSERT INTO public.event_coordinator_assignments (
        event_request_id,
        coordinator_id,
        assigned_by
    )
    VALUES (
        p_event_request_id,
        p_coordinator_id,
        p_assigned_by
    )
    RETURNING * INTO v_assignment;

    RETURN v_assignment;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.assign_event_request_coordinator(
    uuid, varchar, varchar
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.assign_event_request_coordinator(
    uuid, varchar, varchar
) TO service_role;

