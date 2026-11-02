-- Hotfix 2 (H8): who may request a venue booking, and when. Run once, after 0089.
--
-- SCRUM-32 AC7: a booking request is allowed only for an event in Approved, Planning or
-- Safety Review (replacing a venue on a Confirmed event is SCRUM-63's). 0081 refused a list of
-- closed statuses, so Submitted, Under Review, Changes Requested and Confirmed got through.
-- SCRUM-32 AC6: a start date before today in Singapore time is refused. Nothing checked it.
-- SCRUM-32 AC2: the snapshot takes the event's accessibility needs as well as its name,
-- attendance and venue requirements; the caller cannot supply them and a later edit of the
-- event does not rewrite them.
--
-- create_replacement_venue_booking_request stores its request through the same creator, and a
-- replacement must keep working for a Confirmed event and for a booking that has already
-- started. So the body moves to private.insert_venue_booking_request with a replacement flag:
-- the public creator calls it as a new request (all three rules), the replacement function as a
-- replacement (the status rule of 0081, no start-date rule). Both public functions keep their
-- signatures and grants. 0081 and 0068 are not edited: both functions are replaced here.

ALTER TABLE public.venue_booking_requests
    ADD COLUMN IF NOT EXISTS accessibility_needs text;

CREATE OR REPLACE FUNCTION private.insert_venue_booking_request(p_booking jsonb, p_expected_event_updated_at timestamp with time zone, p_replacement boolean)
 RETURNS venue_booking_requests
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    v_key text;
    v_id uuid;
    v_venue_id uuid;
    v_event_id uuid;
    v_requested_by uuid;
    v_start_date date;
    v_end_date date;
    v_start_minute integer;
    v_end_minute integer;
    v_created_at timestamptz;
    v_coordinator varchar;
    v_event public.event_requests%ROWTYPE;
    v_booking public.venue_booking_requests%ROWTYPE;
BEGIN
    IF pg_catalog.jsonb_typeof(p_booking) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'A booking object is required' USING ERRCODE = '22023';
    END IF;
    IF p_booking ->> 'status' IS DISTINCT FROM 'pending' OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_each(p_booking) AS supplied(key, value)
        WHERE key IN ('decision_reason', 'suggested_alternative', 'decided_by',
                      'decided_at', 'cancelled_by', 'cancelled_at')
          AND value <> 'null'::jsonb
    ) THEN
        RAISE EXCEPTION 'A new booking must be Pending without decision or cancellation audit'
            USING ERRCODE = '22023';
    END IF;
    FOREACH v_key IN ARRAY ARRAY[
        'id', 'venue_id', 'event_request_id', 'requested_by', 'start_date', 'end_date'
    ] LOOP
        IF pg_catalog.jsonb_typeof(p_booking -> v_key) IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'Booking identities and dates are required' USING ERRCODE = '22023';
        END IF;
    END LOOP;
    IF pg_catalog.jsonb_typeof(p_booking -> 'start_minute') IS DISTINCT FROM 'number'
       OR pg_catalog.jsonb_typeof(p_booking -> 'end_minute') IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION 'Booking minutes are required' USING ERRCODE = '22023';
    END IF;
    BEGIN
        v_id := (p_booking ->> 'id')::uuid;
        v_venue_id := (p_booking ->> 'venue_id')::uuid;
        v_event_id := (p_booking ->> 'event_request_id')::uuid;
        v_requested_by := (p_booking ->> 'requested_by')::uuid;
        v_start_date := (p_booking ->> 'start_date')::date;
        v_end_date := (p_booking ->> 'end_date')::date;
        v_start_minute := (p_booking ->> 'start_minute')::integer;
        v_end_minute := (p_booking ->> 'end_minute')::integer;
        v_created_at := COALESCE((p_booking ->> 'created_at')::timestamptz,
                                 pg_catalog.transaction_timestamp());
    EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format
                   OR datetime_field_overflow OR numeric_value_out_of_range THEN
        RAISE EXCEPTION 'Invalid booking values' USING ERRCODE = '22023';
    END;
    IF v_end_date < v_start_date OR v_start_minute < 420 OR v_end_minute > 1440
       OR v_start_minute % 15 <> 0 OR v_end_minute % 15 <> 0
       OR v_end_minute <= v_start_minute THEN
        RAISE EXCEPTION 'Booking dates or minutes break the booking rules' USING ERRCODE = '22023';
    END IF;
    -- SCRUM-32 AC6: a new request cannot start before today in Singapore. A replacement keeps the
    -- dates of the booking it replaces, which may already have begun (SCRUM-63).
    IF NOT p_replacement
       AND v_start_date < (pg_catalog.now() AT TIME ZONE 'Asia/Singapore')::date THEN
        RAISE EXCEPTION 'Booking start date is before today' USING ERRCODE = '22023';
    END IF;

    -- Venue first matches approval/block writers. The event lock then joins
    -- assignment, event-version and future date-approval membership changes.
    PERFORM 1 FROM public.venues WHERE id = v_venue_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Venue not found' USING ERRCODE = 'P0002';
    END IF;
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = v_event_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event request not found' USING ERRCODE = 'P0002';
    END IF;
    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = v_event_id ORDER BY id DESC LIMIT 1;
    IF v_coordinator IS DISTINCT FROM v_requested_by::text THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    IF p_expected_event_updated_at IS NULL
       OR v_event.updated_at IS DISTINCT FROM p_expected_event_updated_at THEN
        RAISE EXCEPTION 'Event request changed; refresh before booking' USING ERRCODE = 'P0004';
    END IF;
    -- SCRUM-32 AC7: a new request only in Approved, Planning or Safety Review. A replacement
    -- (SCRUM-63) also serves an event that is already Confirmed, so it keeps the earlier rule:
    -- refused only where the event cannot use a venue at all.
    IF p_replacement THEN
        IF v_event.status IN ('Draft', 'Completed', 'Cancelled', 'Rejected', 'Withdrawn', 'Postponed') THEN
            RAISE EXCEPTION 'Event is not open for venue bookings' USING ERRCODE = 'P0004';
        END IF;
    ELSIF v_event.status NOT IN ('Approved', 'Planning', 'Safety Review') THEN
        RAISE EXCEPTION 'Event is not open for venue bookings' USING ERRCODE = 'P0004';
    END IF;

    -- The authenticated backend supplies identities, dates and minutes. Event
    -- metadata comes only from the locked row; slots remain derived by 0050.
    INSERT INTO public.venue_booking_requests (
        id, venue_id, requested_by, event_request_id, event_name,
        expected_attendance, requirements_note, accessibility_needs, start_date, end_date,
        start_minute, end_minute, status, created_at
    ) VALUES (
        v_id, v_venue_id, v_requested_by, v_event_id, v_event.event_name,
        v_event.expected_attendance, v_event.venue_requirements, v_event.accessibility_needs,
        v_start_date, v_end_date,
        v_start_minute, v_end_minute, 'pending', v_created_at
    ) RETURNING * INTO v_booking;
    RETURN v_booking;
END;
$function$;

REVOKE ALL ON FUNCTION private.insert_venue_booking_request(jsonb, timestamptz, boolean)
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.create_event_venue_booking_request(
    p_booking jsonb,
    p_expected_event_updated_at timestamptz
)
RETURNS public.venue_booking_requests
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT * FROM private.insert_venue_booking_request(p_booking, p_expected_event_updated_at, false);
$$;

REVOKE ALL ON FUNCTION public.create_event_venue_booking_request(jsonb, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_event_venue_booking_request(jsonb, timestamptz)
    TO service_role;

CREATE OR REPLACE FUNCTION public.create_replacement_venue_booking_request(
    p_replaces_booking_id uuid,
    p_new_id uuid,
    p_venue_id uuid,
    p_requested_by uuid,
    p_expected_event_updated_at timestamptz
)
RETURNS public.venue_booking_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_old public.venue_booking_requests%ROWTYPE;
    v_new public.venue_booking_requests%ROWTYPE;
BEGIN
    SELECT * INTO v_old FROM public.venue_booking_requests AS b WHERE b.id = p_replaces_booking_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'booking request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_old.status <> 'approved' THEN
        RAISE EXCEPTION 'booking is not approved' USING ERRCODE = 'P0004';
    END IF;
    IF v_old.venue_id = p_venue_id THEN
        RAISE EXCEPTION 'a replacement must be at a different venue' USING ERRCODE = '22023';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.arrangement_reviews AS r
        WHERE r.arrangement = 'venue_booking' AND r.arrangement_id = p_replaces_booking_id
          AND r.trigger_type = 'venue_block' AND r.cleared_at IS NULL
    ) THEN
        RAISE EXCEPTION 'booking is not flagged as needing a new venue' USING ERRCODE = 'P0004';
    END IF;

    -- Venue and event locks, coordinator and version checks, canonical event metadata.
    v_new := private.insert_venue_booking_request(
        pg_catalog.jsonb_build_object(
            'id', p_new_id,
            'venue_id', p_venue_id,
            'event_request_id', v_old.event_request_id,
            'requested_by', p_requested_by,
            'start_date', v_old.start_date,
            'end_date', v_old.end_date,
            'start_minute', v_old.start_minute,
            'end_minute', v_old.end_minute,
            'status', 'pending'
        ),
        p_expected_event_updated_at,
        true
    );

    -- The replaced booking last, then check it again: it may have changed meanwhile.
    SELECT * INTO v_old
    FROM public.venue_booking_requests AS b
    WHERE b.id = p_replaces_booking_id
    FOR UPDATE;
    IF v_old.status <> 'approved' THEN
        RAISE EXCEPTION 'booking is not approved' USING ERRCODE = 'P0004';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.arrangement_reviews AS r
        WHERE r.arrangement = 'venue_booking' AND r.arrangement_id = p_replaces_booking_id
          AND r.trigger_type = 'venue_block' AND r.cleared_at IS NULL
    ) THEN
        RAISE EXCEPTION 'booking is not flagged as needing a new venue' USING ERRCODE = 'P0004';
    END IF;

    UPDATE public.venue_booking_requests AS b
    SET replaces_booking_id = p_replaces_booking_id
    WHERE b.id = v_new.id
    RETURNING * INTO v_new;
    RETURN v_new;
END;
$$;

REVOKE ALL ON FUNCTION public.create_replacement_venue_booking_request(
    uuid, uuid, uuid, uuid, timestamptz
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_replacement_venue_booking_request(
    uuid, uuid, uuid, uuid, timestamptz
) TO service_role;
