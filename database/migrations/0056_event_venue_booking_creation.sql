-- SCRUM-35 date-approval prerequisite: serialise booking membership creation.
-- Deploy with the matching venueService creator: direct REST INSERT is retired.
-- Existing creation states remain allowed; this does not approve/reschedule an event.
CREATE OR REPLACE FUNCTION public.create_event_venue_booking_request(
    p_booking jsonb,
    p_expected_event_updated_at timestamptz
)
RETURNS public.venue_booking_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
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

    -- The authenticated backend supplies identities, dates and minutes. Event
    -- metadata comes only from the locked row; slots remain derived by 0050.
    INSERT INTO public.venue_booking_requests (
        id, venue_id, requested_by, event_request_id, event_name,
        expected_attendance, requirements_note, start_date, end_date,
        start_minute, end_minute, status, created_at
    ) VALUES (
        v_id, v_venue_id, v_requested_by, v_event_id, v_event.event_name,
        v_event.expected_attendance, v_event.venue_requirements, v_start_date, v_end_date,
        v_start_minute, v_end_minute, 'pending', v_created_at
    ) RETURNING * INTO v_booking;
    RETURN v_booking;
END;
$$;
REVOKE ALL ON FUNCTION public.create_event_venue_booking_request(jsonb, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_event_venue_booking_request(jsonb, timestamptz)
    TO service_role;

-- SECURITY DEFINER is limited to this validated creator because the service
-- role must no longer bypass its version check through direct INSERT/DELETE.
REVOKE INSERT, DELETE ON TABLE public.venue_booking_requests
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION private.protect_venue_booking_membership()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF NEW.event_request_id IS DISTINCT FROM OLD.event_request_id
       OR NEW.venue_id IS DISTINCT FROM OLD.venue_id THEN
        RAISE EXCEPTION 'Booking event and venue cannot be changed' USING ERRCODE = '22023';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.protect_venue_booking_membership()
    FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER protect_venue_booking_membership
    BEFORE UPDATE OF event_request_id, venue_id ON public.venue_booking_requests
    FOR EACH ROW EXECUTE FUNCTION private.protect_venue_booking_membership();
