-- Release 1 hotfixes 21 and 22: two event statuses the customer asked for. Run once,
-- after 0079.
--
-- Q&A #103: the Organiser asks the Coordinator, outside the system, to withdraw a
-- submitted request that is under review; the Coordinator records the withdrawal; a
-- withdrawn request must be distinguishable from draft, submitted, approved, rejected
-- and the other states. -> 'Withdrawn', set by the assigned Coordinator.
--
-- Q&A #69 and #121: an event may be postponed without a new date; its current bookings
-- are released and the record is kept until a new date is given. -> 'Postponed'
-- (0081 adds the functions that postpone and resume).
--
-- Both are added to the status list here, and the Coordinator transition function now
-- accepts Withdrawn (from Submitted, Under Review or Changes Requested) and lets a
-- Postponed event be cancelled. Nothing else about the function changes.

ALTER TABLE public.event_requests
    DROP CONSTRAINT IF EXISTS event_requests_status_check,
    ADD CONSTRAINT event_requests_status_check
        CHECK (status IN (
            'Draft', 'Submitted', 'Under Review', 'Changes Requested', 'Approved',
            'Planning', 'Safety Review', 'Confirmed', 'Completed', 'Cancelled',
            'Rejected', 'Withdrawn', 'Postponed'
        ));

CREATE OR REPLACE FUNCTION public.advance_event_request_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id character varying,
    p_to_status character varying
)
RETURNS public.event_requests
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
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
            p_to_status = 'Withdrawn'
            AND v_current.status IN ('Submitted', 'Under Review', 'Changes Requested')
        )
        OR (
            p_to_status = 'Cancelled'
            AND v_current.status IN (
                'Submitted', 'Under Review', 'Changes Requested',
                'Approved', 'Planning', 'Safety Review', 'Confirmed', 'Postponed'
            )
        )
    ) THEN
        RAISE EXCEPTION 'transition not allowed from status %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.' || CASE p_to_status
            WHEN 'Under Review' THEN 'review' WHEN 'Planning' THEN 'planning'
            WHEN 'Completed' THEN 'completion' WHEN 'Withdrawn' THEN 'withdrawal'
            ELSE 'cancellation' END);
    UPDATE public.event_requests
    SET status = p_to_status
    WHERE id = p_event_request_id
      AND status = v_current.status
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$function$;
