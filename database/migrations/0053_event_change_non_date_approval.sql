-- SCRUM-35: apply only the accepted non-date proposal through one server transaction.
-- Keep the rejection-only RPC and retained legacy primitive unchanged. Existing
-- SCRUM-64 event-update/enqueue triggers capture review work atomically; their
-- recorded update UUID is distinct from this proposal's identity.
CREATE OR REPLACE FUNCTION public.approve_non_date_event_change_request(
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
    v_key text;
    v_value jsonb;
    v_number numeric;
    v_text text;
    v_attendance integer;
    v_venue text;
    v_equipment text;
    v_reason text := pg_catalog.regexp_replace(
        p_reason, '^[[:space:]]+|[[:space:]]+$', '', 'g'
    );
BEGIN
    -- Consistent event-first order also serialises competing decisions.
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC LIMIT 1;
    IF p_coordinator_id IS NULL OR pg_catalog.btrim(p_coordinator_id) = ''
       OR v_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    SELECT * INTO v_change FROM public.event_change_requests
    WHERE id = p_change_request_id AND event_request_id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_change.status <> 'Pending' OR v_event.status NOT IN ('Approved', 'Planning') THEN
        RAISE EXCEPTION 'Change request cannot be approved in its current state'
            USING ERRCODE = 'P0004';
    END IF;
    IF v_event.updated_at IS DISTINCT FROM v_change.base_event_updated_at THEN
        RAISE EXCEPTION 'Change request is stale' USING ERRCODE = 'P0004';
    END IF;
    IF pg_catalog.char_length(v_reason) > 2000 THEN
        RAISE EXCEPTION 'Decision reason must be at most 2000 characters'
            USING ERRCODE = '22023';
    END IF;

    -- Validate the whole proposal before any writes. Never partly apply a mixed
    -- date/registration proposal or coerce malformed stored values into a plan.
    IF pg_catalog.jsonb_typeof(v_change.proposed_changes) IS DISTINCT FROM 'object'
       OR v_change.proposed_changes = '{}'::jsonb THEN
        RAISE EXCEPTION 'Unsupported proposed changes' USING ERRCODE = 'P0004';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(v_change.proposed_changes) AS proposed(key)
        WHERE key NOT IN ('expected_attendance', 'venue_requirements', 'equipment_requirements')
    ) THEN
        RAISE EXCEPTION 'Unsupported proposed changes' USING ERRCODE = 'P0004';
    END IF;

    v_attendance := v_event.expected_attendance;
    v_venue := v_event.venue_requirements;
    v_equipment := v_event.equipment_requirements;
    FOR v_key, v_value IN SELECT key, value FROM pg_catalog.jsonb_each(v_change.proposed_changes) LOOP
        IF v_key = 'expected_attendance' THEN
            IF pg_catalog.jsonb_typeof(v_value) IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'Invalid proposed attendance' USING ERRCODE = 'P0004';
            END IF;
            BEGIN
                v_number := (v_value #>> '{}')::numeric;
            EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
                RAISE EXCEPTION 'Invalid proposed attendance' USING ERRCODE = 'P0004';
            END;
            -- Match the positive integer API rule and the stored integer range.
            IF v_number <= 0 OR v_number > 2147483647
               OR v_number <> pg_catalog.trunc(v_number) THEN
                RAISE EXCEPTION 'Invalid proposed attendance' USING ERRCODE = 'P0004';
            END IF;
            v_attendance := v_number::integer;
        ELSE
            IF pg_catalog.jsonb_typeof(v_value) IS DISTINCT FROM 'string' THEN
                RAISE EXCEPTION 'Invalid proposed requirements' USING ERRCODE = 'P0004';
            END IF;
            v_text := pg_catalog.regexp_replace(
                v_value #>> '{}', '^[[:space:]]+|[[:space:]]+$', '', 'g'
            );
            IF v_text = '' OR pg_catalog.char_length(v_text) > 2000 THEN
                RAISE EXCEPTION 'Invalid proposed requirements' USING ERRCODE = 'P0004';
            END IF;
            IF v_key = 'venue_requirements' THEN
                v_venue := v_text;
            ELSE
                v_equipment := v_text;
            END IF;
        END IF;
    END LOOP;

    IF v_attendance IS NOT DISTINCT FROM v_event.expected_attendance
       AND NULLIF(pg_catalog.btrim(v_venue), '') IS NOT DISTINCT FROM NULLIF(pg_catalog.btrim(v_event.venue_requirements), '')
       AND NULLIF(pg_catalog.btrim(v_equipment), '') IS NOT DISTINCT FROM NULLIF(pg_catalog.btrim(v_event.equipment_requirements), '') THEN
        RAISE EXCEPTION 'At least one proposed value must differ' USING ERRCODE = 'P0004';
    END IF;

    -- No lifecycle, date, booking or reservation update. A flag/enqueue failure
    -- aborts this event update and the decision together, including prior flags.
    UPDATE public.event_requests SET
        expected_attendance = v_attendance,
        venue_requirements = v_venue,
        equipment_requirements = v_equipment,
        updated_at = GREATEST(pg_catalog.clock_timestamp(), updated_at + interval '1 microsecond')
    WHERE id = p_event_request_id;

    UPDATE public.event_change_requests SET
        status = 'Approved',
        coordinator_id = p_coordinator_id,
        decision_reason = NULLIF(v_reason, ''),
        decided_at = pg_catalog.clock_timestamp()
    WHERE id = v_change.id
    RETURNING * INTO v_change;
    RETURN v_change;
END;
$$;

REVOKE ALL ON FUNCTION public.approve_non_date_event_change_request(uuid, uuid, varchar, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.approve_non_date_event_change_request(uuid, uuid, varchar, text)
    TO service_role;
