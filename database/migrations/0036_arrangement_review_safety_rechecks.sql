-- SCRUM-64 AC7: explicit review work inside a trusted saved-decision transaction.
-- The privileged caller must verify the saved decision, roles and immutable
-- event/target/reason payload. No safety decision schema or lifecycle is owned here.
CREATE OR REPLACE FUNCTION private.raise_safety_arrangement_reviews(
    p_event_request_id uuid,
    p_decision_id uuid,
    p_targets jsonb,
    p_reason text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_input jsonb;
    v_target record;
    v_target_id uuid;
    v_inserted integer;
BEGIN
    IF p_event_request_id IS NULL OR p_decision_id IS NULL
       OR p_targets IS NULL OR pg_catalog.jsonb_typeof(p_targets) <> 'array'
       OR p_reason IS NULL OR p_reason ~ '^[[:space:]]*$' THEN
        RAISE EXCEPTION 'Invalid safety review arguments' USING ERRCODE = '22023';
    END IF;
    PERFORM 1 FROM public.event_requests WHERE id = p_event_request_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Arrangement review targets not found' USING ERRCODE = 'P0002';
    END IF;

    -- Parse the entire batch before acquiring target locks or attempting inserts.
    FOR v_input IN SELECT value FROM pg_catalog.jsonb_array_elements(p_targets) LOOP
        IF pg_catalog.jsonb_typeof(v_input) <> 'object' THEN
            RAISE EXCEPTION 'Invalid safety review targets' USING ERRCODE = '22023';
        END IF;
        IF pg_catalog.jsonb_typeof(v_input->'arrangement') IS DISTINCT FROM 'string'
           OR pg_catalog.jsonb_typeof(v_input->'id') IS DISTINCT FROM 'string'
           OR v_input->>'arrangement' NOT IN ('venue_booking', 'equipment_reservation') THEN
            RAISE EXCEPTION 'Invalid safety review targets' USING ERRCODE = '22023';
        END IF;
        BEGIN
            v_target_id := (v_input->>'id')::uuid;
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE EXCEPTION 'Invalid safety review targets' USING ERRCODE = '22023';
        END;
    END LOOP;

    -- Lock each distinct explicit target in the same domain/UUID order. FOR SHARE
    -- protects event membership until the caller transaction ends; it does not
    -- establish a general event/equipment/readiness lock protocol.
    FOR v_target IN
        SELECT DISTINCT value->>'arrangement' AS arrangement,
                        (value->>'id')::uuid AS id
        FROM pg_catalog.jsonb_array_elements(p_targets)
        ORDER BY arrangement, id
    LOOP
        IF v_target.arrangement = 'venue_booking' THEN
            PERFORM 1 FROM public.venue_booking_requests
            WHERE id = v_target.id AND event_request_id = p_event_request_id
            FOR SHARE;
        ELSE
            PERFORM 1 FROM public.equipment_reservations
            WHERE id = v_target.id AND event_request_id = p_event_request_id
            FOR SHARE;
        END IF;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Arrangement review targets not found' USING ERRCODE = 'P0002';
        END IF;
    END LOOP;

    -- Never reopen a cleared row or rewrite original evidence on exact replay.
    -- The caller binds the complete payload to its saved decision; this key alone
    -- does not prevent that caller from supplying additional targets on a replay.
    INSERT INTO public.arrangement_reviews
        (event_request_id, arrangement, arrangement_id, trigger_id,
         trigger_type, changed_fields, reason)
    SELECT p_event_request_id, target.arrangement, target.id, p_decision_id,
           'safety_recheck', '{}'::text[], p_reason
    FROM (
        SELECT DISTINCT value->>'arrangement' AS arrangement,
                        (value->>'id')::uuid AS id
        FROM pg_catalog.jsonb_array_elements(p_targets)
    ) AS target
    ORDER BY target.arrangement, target.id
    ON CONFLICT ON CONSTRAINT arrangement_reviews_trigger_target_unique DO NOTHING;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RETURN v_inserted;
END;
$$;
REVOKE ALL ON FUNCTION private.raise_safety_arrangement_reviews(uuid, uuid, jsonb, text)
    FROM PUBLIC, anon, authenticated, service_role;
