-- SCRUM-35: atomic complete date/time approval. Requires0056+0058 (apply56→58→59).
-- Preserve original migrations, organiser proposal and resource identity/audit.
-- No historical backfill, reservation reallocation or automatic review clearing.
-- SCRUM-35: actual event-date changes require review of every linked reservation,
-- including expired reservations. Non-date edits retain the upcoming-only rule.
-- Preserve the existing single native event-update identity and both domains.
CREATE OR REPLACE FUNCTION private.record_event_arrangement_reviews()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_common_fields text[] := '{}';
    v_common_reasons text[] := '{}';
    v_venue_fields text[];
    v_venue_reasons text[];
    v_equipment_fields text[];
    v_equipment_reasons text[];
    v_trigger_id uuid;
    v_today date := (pg_catalog.transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
BEGIN
    IF NEW.status IN ('Draft', 'Completed', 'Cancelled', 'Rejected') THEN
        RETURN NEW;
    END IF;

    -- timestamptz equality compares instants, including different UTC offsets.
    -- Preserve array order; no set/reordering semantics are imposed on event dates.
    IF NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times THEN
        v_common_fields := pg_catalog.array_append(v_common_fields, 'proposed_date_times');
        v_common_reasons := pg_catalog.array_append(v_common_reasons, pg_catalog.format(
            'proposed_date_times (Asia/Singapore): %s -> %s',
            ARRAY(SELECT d AT TIME ZONE 'Asia/Singapore' FROM pg_catalog.unnest(OLD.proposed_date_times) AS d),
            ARRAY(SELECT d AT TIME ZONE 'Asia/Singapore' FROM pg_catalog.unnest(NEW.proposed_date_times) AS d)
        ));
    END IF;
    IF NEW.expected_attendance IS DISTINCT FROM OLD.expected_attendance THEN
        v_common_fields := pg_catalog.array_append(v_common_fields, 'expected_attendance');
        v_common_reasons := pg_catalog.array_append(v_common_reasons, pg_catalog.format(
            'expected_attendance: %L -> %L', OLD.expected_attendance, NEW.expected_attendance
        ));
    END IF;
    v_venue_fields := v_common_fields;
    v_venue_reasons := v_common_reasons;
    v_equipment_fields := v_common_fields;
    v_equipment_reasons := v_common_reasons;

    -- Optional blank text is equivalent to absent text, as in the API normaliser.
    IF nullif(pg_catalog.btrim(NEW.venue_requirements), '')
       IS DISTINCT FROM nullif(pg_catalog.btrim(OLD.venue_requirements), '') THEN
        v_venue_fields := pg_catalog.array_append(v_venue_fields, 'venue_requirements');
        v_venue_reasons := pg_catalog.array_append(v_venue_reasons, pg_catalog.format(
            'venue_requirements: %L -> %L', OLD.venue_requirements, NEW.venue_requirements
        ));
    END IF;
    IF nullif(pg_catalog.btrim(NEW.equipment_requirements), '')
       IS DISTINCT FROM nullif(pg_catalog.btrim(OLD.equipment_requirements), '') THEN
        v_equipment_fields := pg_catalog.array_append(v_equipment_fields, 'equipment_requirements');
        v_equipment_reasons := pg_catalog.array_append(v_equipment_reasons, pg_catalog.format(
            'equipment_requirements: %L -> %L', OLD.equipment_requirements, NEW.equipment_requirements
        ));
    END IF;
    IF pg_catalog.cardinality(v_venue_fields) = 0
       AND pg_catalog.cardinality(v_equipment_fields) = 0 THEN
        RETURN NEW;
    END IF;

    -- One recorded direct-update identity spans both domains; it is not a
    -- fabricated change_request_id. Each later update receives a distinct UUID.
    v_trigger_id := pg_catalog.gen_random_uuid();
    IF pg_catalog.cardinality(v_venue_fields) > 0 THEN
        INSERT INTO public.arrangement_reviews
            (event_request_id, arrangement, arrangement_id, trigger_id,
             trigger_type, changed_fields, reason)
        SELECT NEW.id, 'venue_booking', b.id, v_trigger_id, 'event_change',
               v_venue_fields, pg_catalog.array_to_string(v_venue_reasons, '; ')
        FROM public.venue_booking_requests AS b
        WHERE b.event_request_id = NEW.id AND b.status = 'approved'
          AND b.end_date >= v_today;
    END IF;
    IF pg_catalog.cardinality(v_equipment_fields) > 0 THEN
        INSERT INTO public.arrangement_reviews
            (event_request_id, arrangement, arrangement_id, trigger_id,
             trigger_type, changed_fields, reason)
        SELECT NEW.id, 'equipment_reservation', r.id, v_trigger_id, 'event_change',
               v_equipment_fields, pg_catalog.array_to_string(v_equipment_reasons, '; ')
        FROM public.equipment_reservations AS r
        WHERE r.event_request_id = NEW.id
          AND (r.return_date >= v_today
               OR NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times);
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.record_event_arrangement_reviews()
    FROM PUBLIC, anon, authenticated, service_role;

-- Nullable evidence for accepted ranges; retained proposals and old rows stay unchanged.
ALTER TABLE public.event_change_requests
    ADD COLUMN applied_booking_plan jsonb
        CHECK (applied_booking_plan IS NULL OR jsonb_typeof(applied_booking_plan) = 'array');
COMMENT ON COLUMN public.event_change_requests.applied_booking_plan IS
    'Canonical complete ranges actually accepted by date approval; not the original organiser proposal.';

CREATE OR REPLACE FUNCTION public.approve_date_event_change_request(
    p_event_request_id uuid,
    p_change_request_id uuid,
    p_coordinator_id varchar,
    p_reason text,
    p_booking_plan jsonb DEFAULT NULL
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
    v_ids uuid[];
    v_venues uuid[];
    v_current_ids uuid[];
    v_plan_ids uuid[] := '{}';
    v_venue_id uuid;
    v_booking_id uuid;
    v_plan jsonb := '[]';
    v_item jsonb;
    v_key text;
    v_value jsonb;
    v_new_dates timestamptz[] := '{}';
    v_date timestamptz;
    v_old_anchor timestamptz;
    v_new_anchor timestamptz;
    v_shift integer;
    v_start date;
    v_end date;
    v_start_minute integer;
    v_end_minute integer;
    v_number numeric;
    v_text text;
    v_attendance integer;
    v_venue_text text;
    v_equipment_text text;
    v_registration_text text;
    v_reason text := pg_catalog.regexp_replace(p_reason, '^[[:space:]]+|[[:space:]]+$', '', 'g');
    v_candidate record;
    v_venue public.venues%ROWTYPE;
    v_guard jsonb;
    v_codes text[];
    v_conflicts uuid[];
    v_pairs uuid[];
    v_blocks uuid[];
    v_issues jsonb := '[]';
BEGIN
    -- Discovery is deliberately unlocked. Never acquire a newly discovered
    -- venue after the event lock: a changed membership must retry instead.
    SELECT coalesce(array_agg(id ORDER BY id), '{}'),
           coalesce(array_agg(DISTINCT venue_id ORDER BY venue_id), '{}')
    INTO v_ids, v_venues
    FROM public.venue_booking_requests
    WHERE event_request_id = p_event_request_id AND status IN ('pending', 'approved');
    FOREACH v_venue_id IN ARRAY v_venues LOOP
        PERFORM 1 FROM public.venues WHERE id = v_venue_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Booking membership changed; refresh the proposal' USING ERRCODE = 'P0004';
        END IF;
    END LOOP;
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;
    SELECT coordinator_id INTO v_coordinator FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id ORDER BY id DESC LIMIT 1;
    IF p_coordinator_id IS NULL OR pg_catalog.btrim(p_coordinator_id) = ''
       OR v_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    SELECT * INTO v_change FROM public.event_change_requests
    WHERE id = p_change_request_id AND event_request_id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_change.status <> 'Pending' OR v_event.status NOT IN ('Approved', 'Planning')
       OR v_event.updated_at IS DISTINCT FROM v_change.base_event_updated_at THEN
        RAISE EXCEPTION 'Change request is stale or cannot be approved' USING ERRCODE = 'P0004';
    END IF;
    IF pg_catalog.char_length(v_reason) > 2000 THEN
        RAISE EXCEPTION 'Decision reason must be at most 2000 characters' USING ERRCODE = '22023';
    END IF;

    -- Lock the discovered rows, including any that were just cancelled, before
    -- comparing the complete current eligible set. Creation uses 0056's event
    -- lock/version check; supported reparenting/deletion bypasses are denied.
    PERFORM 1 FROM public.venue_booking_requests
    WHERE event_request_id = p_event_request_id AND id = ANY(v_ids)
    ORDER BY id FOR UPDATE;
    SELECT coalesce(array_agg(id ORDER BY id), '{}') INTO v_current_ids
    FROM public.venue_booking_requests
    WHERE event_request_id = p_event_request_id AND status IN ('pending', 'approved');
    IF v_current_ids IS DISTINCT FROM v_ids THEN
        RAISE EXCEPTION 'Booking membership changed; refresh the proposal' USING ERRCODE = 'P0004';
    END IF;

    -- Validate the stored proposal, not client-supplied before/after snapshots.
    IF pg_catalog.jsonb_typeof(v_change.proposed_changes) IS DISTINCT FROM 'object'
       OR NOT (v_change.proposed_changes ? 'proposed_date_times') OR EXISTS (
           SELECT 1 FROM pg_catalog.jsonb_object_keys(v_change.proposed_changes) AS k(key)
           WHERE key NOT IN ('proposed_date_times', 'expected_attendance',
               'venue_requirements', 'equipment_requirements', 'registration_needs')
       ) THEN
        RAISE EXCEPTION 'Unsupported proposed changes' USING ERRCODE = 'P0004';
    END IF;
    IF pg_catalog.jsonb_typeof(v_change.proposed_changes -> 'proposed_date_times') IS DISTINCT FROM 'array'
       OR pg_catalog.jsonb_array_length(v_change.proposed_changes -> 'proposed_date_times') = 0 THEN
        RAISE EXCEPTION 'A nonempty event date plan is required' USING ERRCODE = 'P0004';
    END IF;
    FOR v_value IN SELECT value FROM pg_catalog.jsonb_array_elements(v_change.proposed_changes -> 'proposed_date_times') LOOP
        IF pg_catalog.jsonb_typeof(v_value) IS DISTINCT FROM 'string'
           OR (v_value #>> '{}') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
            RAISE EXCEPTION 'Event dates must contain aware instants' USING ERRCODE = 'P0004';
        END IF;
        BEGIN
            v_date := (v_value #>> '{}')::timestamptz;
        EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR datetime_field_overflow THEN
            RAISE EXCEPTION 'Invalid proposed event date' USING ERRCODE = 'P0004';
        END;
        IF NOT pg_catalog.isfinite(v_date) THEN
            RAISE EXCEPTION 'Invalid proposed event date' USING ERRCODE = 'P0004';
        END IF;
        v_new_dates := pg_catalog.array_append(v_new_dates, v_date);
    END LOOP;
    IF v_new_dates IS NOT DISTINCT FROM v_event.proposed_date_times THEN
        RAISE EXCEPTION 'Event dates must change; a duration-only plan is unsupported' USING ERRCODE = 'P0004';
    END IF;
    v_attendance := v_event.expected_attendance;
    v_venue_text := v_event.venue_requirements;
    v_equipment_text := v_event.equipment_requirements;
    v_registration_text := v_event.registration_needs;
    FOR v_key, v_value IN SELECT key, value FROM pg_catalog.jsonb_each(v_change.proposed_changes) LOOP
        IF v_key = 'proposed_date_times' THEN
            CONTINUE;
        ELSIF v_key = 'expected_attendance' THEN
            IF pg_catalog.jsonb_typeof(v_value) IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'Invalid proposed attendance' USING ERRCODE = 'P0004';
            END IF;
            BEGIN
                v_number := (v_value #>> '{}')::numeric;
            EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
                RAISE EXCEPTION 'Invalid proposed attendance' USING ERRCODE = 'P0004';
            END;
            IF v_number <= 0 OR v_number > 2147483647 OR v_number <> pg_catalog.trunc(v_number) THEN
                RAISE EXCEPTION 'Invalid proposed attendance' USING ERRCODE = 'P0004';
            END IF;
            v_attendance := v_number::integer;
        ELSE
            IF pg_catalog.jsonb_typeof(v_value) IS DISTINCT FROM 'string' THEN
                RAISE EXCEPTION 'Invalid proposed requirements' USING ERRCODE = 'P0004';
            END IF;
            v_text := pg_catalog.regexp_replace(v_value #>> '{}', '^[[:space:]]+|[[:space:]]+$', '', 'g');
            IF v_text = '' OR pg_catalog.char_length(v_text) > 2000 THEN
                RAISE EXCEPTION 'Invalid proposed requirements' USING ERRCODE = 'P0004';
            END IF;
            IF v_key = 'venue_requirements' THEN v_venue_text := v_text;
            ELSIF v_key = 'equipment_requirements' THEN v_equipment_text := v_text;
            ELSE v_registration_text := v_text;
            END IF;
        END IF;
    END LOOP;

    IF p_booking_plan IS NULL OR p_booking_plan = 'null'::jsonb THEN
        -- The automatic path preserves corresponding SG wall times, anchor
        -- count/order and one nonzero calendar-day shift, exactly as the preview.
        IF coalesce(pg_catalog.cardinality(v_event.proposed_date_times), 0) = 0
           OR pg_catalog.cardinality(v_event.proposed_date_times) <> pg_catalog.cardinality(v_new_dates) THEN
            RAISE EXCEPTION 'Explicit complete booking plan required' USING ERRCODE = 'P0004';
        END IF;
        SELECT (n.d AT TIME ZONE 'Asia/Singapore')::date - (o.d AT TIME ZONE 'Asia/Singapore')::date
        INTO v_shift
        FROM pg_catalog.unnest(v_event.proposed_date_times) WITH ORDINALITY AS o(d, position)
        JOIN pg_catalog.unnest(v_new_dates) WITH ORDINALITY AS n(d, position) USING (position)
        ORDER BY position LIMIT 1;
        IF v_shift = 0 THEN
            RAISE EXCEPTION 'Explicit complete booking plan required' USING ERRCODE = 'P0004';
        END IF;
        FOR v_old_anchor, v_new_anchor IN
            SELECT o.d, n.d
            FROM pg_catalog.unnest(v_event.proposed_date_times) WITH ORDINALITY AS o(d, position)
            JOIN pg_catalog.unnest(v_new_dates) WITH ORDINALITY AS n(d, position) USING (position)
        LOOP
            IF (v_old_anchor AT TIME ZONE 'Asia/Singapore')::time
                   IS DISTINCT FROM (v_new_anchor AT TIME ZONE 'Asia/Singapore')::time
               OR (v_new_anchor AT TIME ZONE 'Asia/Singapore')::date
                    - (v_old_anchor AT TIME ZONE 'Asia/Singapore')::date <> v_shift THEN
                RAISE EXCEPTION 'Explicit complete booking plan required' USING ERRCODE = 'P0004';
            END IF;
        END LOOP;
        BEGIN
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                'booking_id', id, 'start_date', start_date + v_shift, 'end_date', end_date + v_shift,
                'start_minute', start_minute, 'end_minute', end_minute
            ) ORDER BY id), '[]'::jsonb) INTO v_plan
            FROM public.venue_booking_requests WHERE id = ANY(v_ids);
        EXCEPTION WHEN datetime_field_overflow THEN
            RAISE EXCEPTION 'Unsupported booking date mapping' USING ERRCODE = 'P0004';
        END;
    ELSE
        IF pg_catalog.jsonb_typeof(p_booking_plan) IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'A complete booking plan array is required' USING ERRCODE = '22023';
        END IF;
        FOR v_item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_booking_plan) LOOP
            IF pg_catalog.jsonb_typeof(v_item) IS DISTINCT FROM 'object'
               OR NOT (v_item ?& ARRAY['booking_id', 'start_date', 'end_date', 'start_minute', 'end_minute'])
               OR EXISTS (SELECT 1 FROM pg_catalog.jsonb_object_keys(v_item) AS k(key)
                   WHERE key NOT IN ('booking_id', 'start_date', 'end_date', 'start_minute', 'end_minute')) THEN
                RAISE EXCEPTION 'Invalid complete booking plan' USING ERRCODE = '22023';
            END IF;
            IF pg_catalog.jsonb_typeof(v_item -> 'booking_id') IS DISTINCT FROM 'string'
               OR pg_catalog.jsonb_typeof(v_item -> 'start_date') IS DISTINCT FROM 'string'
               OR pg_catalog.jsonb_typeof(v_item -> 'end_date') IS DISTINCT FROM 'string'
               OR pg_catalog.jsonb_typeof(v_item -> 'start_minute') IS DISTINCT FROM 'number'
               OR pg_catalog.jsonb_typeof(v_item -> 'end_minute') IS DISTINCT FROM 'number'
               OR (v_item ->> 'start_date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
               OR (v_item ->> 'end_date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
                RAISE EXCEPTION 'Invalid booking plan values' USING ERRCODE = '22023';
            END IF;
            BEGIN
                v_booking_id := (v_item ->> 'booking_id')::uuid;
                v_start := (v_item ->> 'start_date')::date;
                v_end := (v_item ->> 'end_date')::date;
                IF (v_item ->> 'start_minute')::numeric <> pg_catalog.trunc((v_item ->> 'start_minute')::numeric)
                   OR (v_item ->> 'end_minute')::numeric <> pg_catalog.trunc((v_item ->> 'end_minute')::numeric) THEN
                    RAISE EXCEPTION 'Booking minutes must be integers' USING ERRCODE = '22023';
                END IF;
                v_start_minute := ((v_item ->> 'start_minute')::numeric)::integer;
                v_end_minute := ((v_item ->> 'end_minute')::numeric)::integer;
            EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format
                           OR datetime_field_overflow OR numeric_value_out_of_range THEN
                RAISE EXCEPTION 'Invalid booking plan values' USING ERRCODE = '22023';
            END;
            IF NOT (v_booking_id = ANY(v_ids)) OR v_booking_id = ANY(v_plan_ids)
               OR v_end < v_start OR v_start_minute < 420 OR v_end_minute > 1440
               OR v_start_minute % 15 <> 0 OR v_end_minute % 15 <> 0
               OR v_end_minute <= v_start_minute THEN
                RAISE EXCEPTION 'Booking plan must cover each current eligible booking exactly once with valid ranges'
                    USING ERRCODE = '22023';
            END IF;
            v_plan_ids := pg_catalog.array_append(v_plan_ids, v_booking_id);
            v_plan := v_plan || jsonb_build_array(jsonb_build_object(
                'booking_id', v_booking_id, 'start_date', v_start, 'end_date', v_end,
                'start_minute', v_start_minute, 'end_minute', v_end_minute
            ));
        END LOOP;
        IF pg_catalog.cardinality(v_plan_ids) <> pg_catalog.cardinality(v_ids) THEN
            RAISE EXCEPTION 'Booking plan must cover every current eligible booking' USING ERRCODE = '22023';
        END IF;
        SELECT coalesce(jsonb_agg(x ORDER BY (x ->> 'booking_id')::uuid), '[]'::jsonb)
        INTO v_plan FROM pg_catalog.jsonb_array_elements(v_plan) AS x;
    END IF;

    -- No writes until all candidates pass. 0054 remains the single external
    -- booking/padding guard; blocks and proposed-vs-proposed pairs add facts it
    -- cannot obtain from stored old times. Refusals do not create refusal rows.
    FOR v_candidate IN
        SELECT b.id AS booking_id, b.venue_id, p.start_date, p.end_date, p.start_minute, p.end_minute
        FROM pg_catalog.jsonb_to_recordset(v_plan) AS p(
            booking_id uuid, start_date date, end_date date, start_minute integer, end_minute integer)
        JOIN public.venue_booking_requests b ON b.id = p.booking_id
        ORDER BY b.id
    LOOP
        SELECT * INTO v_venue FROM public.venues WHERE id = v_candidate.venue_id;
        v_guard := private.check_booking_candidate(v_candidate.venue_id,
            v_candidate.start_date, v_candidate.end_date, v_candidate.start_minute, v_candidate.end_minute, v_ids);
        v_codes := ARRAY(SELECT jsonb_array_elements_text(v_guard -> 'refusal_codes'));
        v_conflicts := ARRAY(SELECT jsonb_array_elements_text(v_guard -> 'conflicting_booking_ids')::uuid);
        IF v_venue.status <> 'available' THEN v_codes := v_codes || 'venue_unavailable'::text; END IF;
        SELECT coalesce(array_agg(b.id ORDER BY b.id), '{}') INTO v_blocks
        FROM public.venue_blocks b
        WHERE b.venue_id = v_candidate.venue_id AND b.status = 'active'
          AND b.start_date <= v_candidate.end_date AND v_candidate.start_date <= b.end_date
          AND b.start_minute < v_candidate.end_minute AND v_candidate.start_minute < b.end_minute;
        IF pg_catalog.cardinality(v_blocks) > 0 THEN v_codes := v_codes || 'active_block'::text; END IF;
        SELECT coalesce(array_agg(p.booking_id ORDER BY p.booking_id), '{}') INTO v_pairs
        FROM pg_catalog.jsonb_to_recordset(v_plan) AS p(
            booking_id uuid, start_date date, end_date date, start_minute integer, end_minute integer)
        JOIN public.venue_booking_requests b ON b.id = p.booking_id
        WHERE p.booking_id <> v_candidate.booking_id AND b.venue_id = v_candidate.venue_id
          AND p.start_date <= v_candidate.end_date AND v_candidate.start_date <= p.end_date
          AND p.start_minute - v_venue.setup_minutes < v_candidate.end_minute + v_venue.turnaround_minutes
          AND v_candidate.start_minute - v_venue.setup_minutes < p.end_minute + v_venue.turnaround_minutes;
        IF pg_catalog.cardinality(v_pairs) > 0 THEN
            IF NOT ('booking_conflict' = ANY(v_codes)) THEN v_codes := v_codes || 'booking_conflict'::text; END IF;
            SELECT ARRAY(SELECT DISTINCT id FROM pg_catalog.unnest(v_conflicts || v_pairs) AS x(id) ORDER BY id)
            INTO v_conflicts;
        END IF;
        IF pg_catalog.cardinality(v_codes) > 0 THEN
            v_issues := v_issues || jsonb_build_array(jsonb_build_object(
                'booking_id', v_candidate.booking_id, 'refusal_codes', v_codes,
                'conflicting_booking_ids', v_conflicts, 'conflicting_block_ids', v_blocks
            ));
        END IF;
    END LOOP;
    IF pg_catalog.jsonb_array_length(v_issues) > 0 THEN
        RAISE EXCEPTION 'One or more venue bookings conflict with the proposed plan'
            USING ERRCODE = 'P0005', DETAIL = v_issues::text;
    END IF;

    UPDATE public.venue_booking_requests b SET
        start_date = p.start_date, end_date = p.end_date,
        start_minute = p.start_minute, end_minute = p.end_minute
    FROM pg_catalog.jsonb_to_recordset(v_plan) AS p(
        booking_id uuid, start_date date, end_date date, start_minute integer, end_minute integer)
    WHERE b.id = p.booking_id AND b.event_request_id = p_event_request_id;
    -- Bookings move first so the existing native review writer sees final dates.
    -- Required domain reviews/jobs and registration evidence share this update.
    UPDATE public.event_requests SET
        proposed_date_times = v_new_dates, expected_attendance = v_attendance,
        venue_requirements = v_venue_text, equipment_requirements = v_equipment_text,
        registration_needs = v_registration_text,
        updated_at = GREATEST(pg_catalog.clock_timestamp(), updated_at + interval '1 microsecond')
    WHERE id = p_event_request_id;
    UPDATE public.event_change_requests SET
        status = 'Approved', coordinator_id = p_coordinator_id,
        decision_reason = NULLIF(v_reason, ''), decided_at = pg_catalog.clock_timestamp(),
        applied_booking_plan = v_plan
    WHERE id = v_change.id RETURNING * INTO v_change;
    RETURN v_change;
END;
$$;
REVOKE ALL ON FUNCTION public.approve_date_event_change_request(uuid, uuid, varchar, text, jsonb)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.approve_date_event_change_request(uuid, uuid, varchar, text, jsonb)
    TO service_role;
