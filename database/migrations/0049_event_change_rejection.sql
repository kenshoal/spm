-- SCRUM-35 rejection-only workflow. The retained approval primitive is unchanged.
-- Lock the event before the proposal, as creation/legacy decisions do. Rejection
-- never applies the proposed values, so its base event version may be older.
CREATE OR REPLACE FUNCTION public.reject_event_change_request(
    p_event_request_id uuid,
    p_change_request_id uuid,
    p_coordinator_id varchar,
    p_reason text
)
RETURNS public.event_change_requests
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
    v_change public.event_change_requests%ROWTYPE;
    v_coordinator varchar;
    v_reason text := pg_catalog.regexp_replace(
        p_reason, '^[[:space:]]+|[[:space:]]+$', '', 'g'
    );
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;

    -- Assignment identities come from the verified backend; NULL must not match
    -- an unassigned event. Identity order is the current assignment contract.
    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;
    IF p_coordinator_id IS NULL OR pg_catalog.btrim(p_coordinator_id) = ''
       OR v_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    SELECT * INTO v_change
    FROM public.event_change_requests
    WHERE id = p_change_request_id AND event_request_id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_change.status <> 'Pending' OR v_event.status NOT IN ('Approved', 'Planning') THEN
        RAISE EXCEPTION 'Change request cannot be rejected in its current state'
            USING ERRCODE = 'P0004';
    END IF;
    IF v_reason IS NULL OR v_reason = '' OR pg_catalog.char_length(v_reason) > 2000 THEN
        RAISE EXCEPTION 'A rejection reason of at most 2000 characters is required'
            USING ERRCODE = '22023';
    END IF;

    -- Only proposal business history changes: no event update means no status
    -- history, arrangement-review trigger or resource mutation is invoked.
    UPDATE public.event_change_requests SET
        status = 'Rejected',
        coordinator_id = p_coordinator_id,
        decision_reason = v_reason,
        decided_at = pg_catalog.clock_timestamp()
    WHERE id = v_change.id
    RETURNING * INTO v_change;
    RETURN v_change;
END;
$$;

REVOKE ALL ON FUNCTION public.reject_event_change_request(uuid, uuid, varchar, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reject_event_change_request(uuid, uuid, varchar, text)
    TO service_role;
