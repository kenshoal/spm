-- Keep optimistic-concurrency tracking correct after an approved amendment.

CREATE OR REPLACE FUNCTION public.decide_event_change_request(
    p_event_request_id uuid,
    p_change_request_id uuid,
    p_coordinator_id varchar,
    p_decision text,
    p_reason text DEFAULT NULL
)
RETURNS public.event_change_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
    v_change public.event_change_requests%ROWTYPE;
    v_assigned_coordinator varchar;
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_assigned_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY assigned_at DESC, id DESC
    LIMIT 1;
    IF v_assigned_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    SELECT * INTO v_change
    FROM public.event_change_requests
    WHERE id = p_change_request_id AND event_request_id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_change.status <> 'Pending' THEN
        RAISE EXCEPTION 'Change request is already decided' USING ERRCODE = 'P0004';
    END IF;
    IF p_decision NOT IN ('Approved', 'Rejected')
       OR (p_decision = 'Rejected' AND coalesce(btrim(p_reason), '') = '') THEN
        RAISE EXCEPTION 'Invalid change decision' USING ERRCODE = 'P0004';
    END IF;

    IF p_decision = 'Approved' AND v_event.updated_at <> v_change.base_event_updated_at THEN
        RAISE EXCEPTION 'Change request is stale' USING ERRCODE = 'P0004';
    END IF;

    IF p_decision = 'Approved' THEN
        UPDATE public.event_requests SET
            proposed_date_times = CASE WHEN v_change.proposed_changes ? 'proposed_date_times'
                THEN ARRAY(SELECT jsonb_array_elements_text(v_change.proposed_changes->'proposed_date_times')::timestamptz)
                ELSE proposed_date_times END,
            expected_attendance = CASE WHEN v_change.proposed_changes ? 'expected_attendance'
                THEN (v_change.proposed_changes->>'expected_attendance')::integer ELSE expected_attendance END,
            venue_requirements = CASE WHEN v_change.proposed_changes ? 'venue_requirements'
                THEN v_change.proposed_changes->>'venue_requirements' ELSE venue_requirements END,
            equipment_requirements = CASE WHEN v_change.proposed_changes ? 'equipment_requirements'
                THEN v_change.proposed_changes->>'equipment_requirements' ELSE equipment_requirements END,
            registration_needs = CASE WHEN v_change.proposed_changes ? 'registration_needs'
                THEN v_change.proposed_changes->>'registration_needs' ELSE registration_needs END,
            updated_at = now()
        WHERE id = p_event_request_id;
    END IF;

    UPDATE public.event_change_requests SET
        status = p_decision,
        coordinator_id = p_coordinator_id,
        decision_reason = NULLIF(btrim(p_reason), ''),
        decided_at = now()
    WHERE id = p_change_request_id
    RETURNING * INTO v_change;
    RETURN v_change;
END;
$$;

REVOKE ALL ON FUNCTION public.decide_event_change_request(uuid, uuid, varchar, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.decide_event_change_request(uuid, uuid, varchar, text, text)
    TO service_role;
