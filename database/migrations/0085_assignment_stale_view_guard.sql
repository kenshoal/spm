-- Hotfix 2 (H7): a reassignment from an out-of-date screen is refused. Run once,
-- after 0084.
--
-- SCRUM-62 AC6: the system refuses a reassignment made from an out-of-date view of the
-- event. The Lead's screen states the Coordinator it showed (null when nobody was
-- assigned); the function compares that with the latest assignment under the same
-- event row lock the assignment already took, so two Leads cannot both win.
--
-- SCRUM-14 AC7 lists Draft, Completed, Cancelled and Rejected. Withdrawn (hotfix 21) is
-- a closed status too, so the function refuses it as well instead of leaving that to
-- the service. Postponed stays assignable: the event is still active (SCRUM-62 AC3).
--
-- The three-argument function is dropped so that nothing can call it and skip the check.

DROP FUNCTION IF EXISTS public.assign_event_request_coordinator(uuid, varchar, varchar);

CREATE FUNCTION public.assign_event_request_coordinator(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_assigned_by varchar,
    p_expected_coordinator_id varchar
)
RETURNS public.event_coordinator_assignments
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_status text;
    v_latest varchar;
    v_assignment public.event_coordinator_assignments;
BEGIN
    SELECT status INTO v_status
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_status IN ('Draft', 'Completed', 'Cancelled', 'Rejected', 'Withdrawn') THEN
        RAISE EXCEPTION 'coordinator assignment not allowed from status %', v_status
            USING ERRCODE = 'P0004';
    END IF;

    SELECT coordinator_id INTO v_latest
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;

    IF v_latest IS DISTINCT FROM p_expected_coordinator_id THEN
        RAISE EXCEPTION 'the coordinator changed since the request was opened'
            USING ERRCODE = 'P0006';
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
    uuid, varchar, varchar, varchar
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.assign_event_request_coordinator(
    uuid, varchar, varchar, varchar
) TO service_role;
