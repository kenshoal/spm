-- Atomic coordinator status transitions (SCRUM-28).
--
-- eventRequestService previously checked the latest assignment and then
-- updated the status as two separate statements, so a reassignment or a
-- concurrent transition between the check and the write could still commit
-- an unauthorized or stale change. This function makes the authorization
-- decision and the status write one statement: the row is locked with
-- FOR UPDATE, the latest assignment is re-read inside the same transaction,
-- and the update is scoped to the status seen under the lock.
--
--   advance_event_request_by_coordinator(p_event_request_id, p_coordinator_id, p_to_status)
--
-- Errcode contract (the service maps on these, never on message text):
--   P0002  event request not found
--   P0003  caller is not the latest-assigned coordinator
--   P0004  transition not allowed from the current status
--
-- Transitions owned by other stories (approval, rejection, changes
-- requested, planning, confirmation, auto-complete) are deliberately not
-- accepted here.
--
-- Residual write-skew: a coordinator (re)assignment INSERT does not take
-- the event_requests row lock, so a reassignment committed between the
-- latest-assignment check and this transaction's commit could leave the
-- status change attributed to a coordinator who is no longer the latest.
-- Closing that fully would need the assignment path to lock the same row.

CREATE FUNCTION advance_event_request_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_to_status varchar
)
RETURNS event_requests
LANGUAGE plpgsql
AS $$
DECLARE
    v_current event_requests;
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
        OR (p_to_status = 'Completed' AND v_current.status = 'Confirmed')
        -- Draft is excluded: drafts carry no assignment (organisers discard
        -- them via DELETE), and Completed/Cancelled/Rejected are terminal.
        OR (
            p_to_status = 'Cancelled'
            AND v_current.status IN (
                'Submitted', 'Under Review', 'Changes Requested',
                'Approved', 'Planning', 'Confirmed'
            )
        )
    ) THEN
        RAISE EXCEPTION 'transition not allowed from status %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    UPDATE public.event_requests
    SET status = p_to_status
    WHERE id = p_event_request_id
      AND status = v_current.status
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$$;

-- The service calls this through its server-only key; no role inherits it
-- through PUBLIC (same defence-in-depth as 0006).
REVOKE EXECUTE ON FUNCTION advance_event_request_by_coordinator(uuid, varchar, varchar) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION advance_event_request_by_coordinator(uuid, varchar, varchar) TO service_role;
