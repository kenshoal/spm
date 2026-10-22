-- SCRUM-35: registration requirements review without attendee/settings mutation.
-- New event-version evidence and acknowledgement are atomic with their source
-- action. No historical backfill, automatic clear or new notification contract.
-- Requires 0046 ordinary readiness, 0053 non-date approval and existing event
-- updated_at triggers. Apply as one transaction; service review reads only.
CREATE TABLE public.event_registration_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL REFERENCES public.event_requests(id) ON DELETE CASCADE,
    event_updated_at timestamptz NOT NULL,
    changed_fields text[] NOT NULL,
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    raised_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    cleared_at timestamptz,
    cleared_by uuid,
    CONSTRAINT event_registration_review_audit_pair CHECK (
        (cleared_at IS NULL) = (cleared_by IS NULL)
    ),
    CONSTRAINT event_registration_review_event_version UNIQUE (event_request_id, event_updated_at)
);
CREATE INDEX event_registration_reviews_event_order
    ON public.event_registration_reviews (event_request_id, raised_at DESC, id DESC);
ALTER TABLE public.event_registration_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.event_registration_reviews FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.event_registration_reviews TO service_role;

-- Only an actual significant event update creates retained registration work.
-- The native trigger owns insertion; service_role cannot fabricate review rows.
CREATE OR REPLACE FUNCTION private.record_event_registration_review()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_fields text[] := '{}';
    v_reasons text[] := '{}';
BEGIN
    IF NEW.status IN ('Draft', 'Completed', 'Cancelled', 'Rejected') THEN
        RETURN NEW;
    END IF;
    IF NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times THEN
        v_fields := pg_catalog.array_append(v_fields, 'proposed_date_times');
        v_reasons := pg_catalog.array_append(v_reasons, pg_catalog.format(
            'proposed_date_times (Asia/Singapore): %s -> %s',
            ARRAY(SELECT d AT TIME ZONE 'Asia/Singapore' FROM pg_catalog.unnest(OLD.proposed_date_times) AS d),
            ARRAY(SELECT d AT TIME ZONE 'Asia/Singapore' FROM pg_catalog.unnest(NEW.proposed_date_times) AS d)
        ));
    END IF;
    IF NEW.expected_attendance IS DISTINCT FROM OLD.expected_attendance THEN
        v_fields := pg_catalog.array_append(v_fields, 'expected_attendance');
        v_reasons := pg_catalog.array_append(v_reasons, pg_catalog.format(
            'expected_attendance: %L -> %L', OLD.expected_attendance, NEW.expected_attendance
        ));
    END IF;
    IF nullif(pg_catalog.regexp_replace(NEW.registration_needs, '^[[:space:]]+|[[:space:]]+$', '', 'g'), '')
       IS DISTINCT FROM nullif(pg_catalog.regexp_replace(OLD.registration_needs, '^[[:space:]]+|[[:space:]]+$', '', 'g'), '') THEN
        v_fields := pg_catalog.array_append(v_fields, 'registration_needs');
        v_reasons := pg_catalog.array_append(v_reasons, pg_catalog.format(
            'registration_needs: %L -> %L', OLD.registration_needs, NEW.registration_needs
        ));
    END IF;
    IF pg_catalog.cardinality(v_fields) = 0 THEN
        RETURN NEW;
    END IF;
    INSERT INTO public.event_registration_reviews
        (event_request_id, event_updated_at, changed_fields, reason)
    VALUES (NEW.id, NEW.updated_at, v_fields, pg_catalog.array_to_string(v_reasons, '; '));
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.record_event_registration_review()
    FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER record_event_registration_review
    AFTER UPDATE OF proposed_date_times, expected_attendance, registration_needs
    ON public.event_requests
    FOR EACH ROW EXECUTE FUNCTION private.record_event_registration_review();

-- Acknowledgement records the current coordinator's check, not a change to
-- attendee registrations, windows, capacity or the event lifecycle.
CREATE OR REPLACE FUNCTION public.acknowledge_event_registration_review(
    p_event_request_id uuid,
    p_review_id uuid,
    p_coordinator_id uuid
)
RETURNS public.event_registration_reviews
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_coordinator varchar;
    v_review public.event_registration_reviews;
BEGIN
    -- Match the event-only gate protocol: event before review, no resource locks.
    PERFORM 1 FROM public.event_requests WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Registration review not found' USING ERRCODE = 'P0002';
    END IF;
    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id ORDER BY id DESC LIMIT 1;
    IF p_coordinator_id IS NULL OR v_coordinator IS DISTINCT FROM p_coordinator_id::text THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    SELECT * INTO v_review FROM public.event_registration_reviews
    WHERE id = p_review_id AND event_request_id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Registration review not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_review.cleared_at IS NOT NULL THEN
        RAISE EXCEPTION 'Registration review already acknowledged' USING ERRCODE = 'P0004';
    END IF;
    UPDATE public.event_registration_reviews
    SET cleared_at = pg_catalog.clock_timestamp(), cleared_by = p_coordinator_id
    WHERE id = v_review.id RETURNING * INTO v_review;
    RETURN v_review;
END;
$$;
REVOKE ALL ON FUNCTION public.acknowledge_event_registration_review(uuid, uuid, uuid)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.acknowledge_event_registration_review(uuid, uuid, uuid)
    TO service_role;

-- Retain ordinary readiness verbatim and append registration evidence.
CREATE OR REPLACE FUNCTION private.event_readiness_issues(p_event_request_id uuid)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT
        CASE WHEN EXISTS (
            SELECT 1 FROM public.venue_booking_requests
            WHERE event_request_id = p_event_request_id AND status IN ('approved', 'pending')
        ) THEN '[]'::jsonb
        ELSE jsonb_build_array(jsonb_build_object('kind', 'no_venue_booking'))
        END
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'venue_booking_pending', 'booking_id', b.id, 'venue_name', v.name
            ) ORDER BY b.created_at, b.id)
            FROM public.venue_booking_requests b
            JOIN public.venues v ON v.id = b.venue_id
            WHERE b.event_request_id = p_event_request_id AND b.status = 'pending'
        ), '[]'::jsonb)
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'equipment_not_reserved', 'requirement_id', r.id,
                'equipment_type', r.equipment_type, 'required', r.quantity, 'reserved', r.reserved
            ) ORDER BY r.recorded_at, r.id)
            FROM (
                SELECT q.id, q.equipment_type, q.quantity, q.recorded_at,
                    coalesce((SELECT sum(s.quantity) FROM public.equipment_reservations s
                              WHERE s.requirement_id = q.id), 0)::int AS reserved
                FROM public.equipment_requirements q
                WHERE q.event_request_id = p_event_request_id
            ) r
            WHERE r.reserved < r.quantity
        ), '[]'::jsonb)
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'arrangement_needs_review', 'arrangement', 'registration',
                'review_id', r.id, 'reason', r.reason
            ) ORDER BY r.raised_at DESC, r.id DESC)
            FROM public.event_registration_reviews r
            WHERE r.event_request_id = p_event_request_id AND r.cleared_at IS NULL
        ), '[]'::jsonb);
$$;

REVOKE ALL ON FUNCTION private.event_readiness_issues(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.event_readiness_issues(uuid) TO service_role;

-- Extend only the narrow non-date approval keyset; 0053 remains unchanged.
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
    v_registration text;
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
    -- date proposal or coerce malformed stored values into a plan.
    IF pg_catalog.jsonb_typeof(v_change.proposed_changes) IS DISTINCT FROM 'object'
       OR v_change.proposed_changes = '{}'::jsonb THEN
        RAISE EXCEPTION 'Unsupported proposed changes' USING ERRCODE = 'P0004';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_object_keys(v_change.proposed_changes) AS proposed(key)
        WHERE key NOT IN ('expected_attendance', 'venue_requirements', 'equipment_requirements', 'registration_needs')
    ) THEN
        RAISE EXCEPTION 'Unsupported proposed changes' USING ERRCODE = 'P0004';
    END IF;

    v_attendance := v_event.expected_attendance;
    v_venue := v_event.venue_requirements;
    v_equipment := v_event.equipment_requirements;
    v_registration := v_event.registration_needs;
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
            ELSIF v_key = 'equipment_requirements' THEN
                v_equipment := v_text;
            ELSE
                v_registration := v_text;
            END IF;
        END IF;
    END LOOP;

    IF v_attendance IS NOT DISTINCT FROM v_event.expected_attendance
       AND NULLIF(pg_catalog.btrim(v_venue), '') IS NOT DISTINCT FROM NULLIF(pg_catalog.btrim(v_event.venue_requirements), '')
       AND NULLIF(pg_catalog.btrim(v_equipment), '') IS NOT DISTINCT FROM NULLIF(pg_catalog.btrim(v_event.equipment_requirements), '')
       AND NULLIF(pg_catalog.btrim(v_registration), '') IS NOT DISTINCT FROM NULLIF(pg_catalog.btrim(v_event.registration_needs), '') THEN
        RAISE EXCEPTION 'At least one proposed value must differ' USING ERRCODE = 'P0004';
    END IF;

    -- No lifecycle, date, booking or reservation update. A flag/enqueue failure
    -- aborts this event update and the decision together, including prior flags.
    UPDATE public.event_requests SET
        expected_attendance = v_attendance,
        venue_requirements = v_venue,
        equipment_requirements = v_equipment,
        registration_needs = v_registration,
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
