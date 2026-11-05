-- Release 1 hotfix 22: postpone an event, with or without a new date. Run once, after 0080.
--
-- Q&A #69 and #121: an event may be postponed even when the new date is not yet known.
-- Its current bookings are released and the event record is kept until a new date is
-- provided. (With a new date already known, the Organiser's change request and the
-- date approval of 0071 already review the affected arrangements.)
--
--   postpone_event_by_coordinator   Approved, Planning, Safety Review or Confirmed ->
--                                   Postponed, with a reason. A trigger then releases the
--                                   event's venue bookings, tentative holds and equipment
--                                   reservations, as cancelling does (0073), but the
--                                   event, its requirements, registrations and history stay.
--   resume_postponed_event          Postponed -> Planning with the new date(s). The
--                                   arrangements were released, so the event is planned and
--                                   confirmed again from here.
--
-- A venue booking request is also refused for an event that cannot use one (Draft,
-- Completed, Cancelled, Rejected, Withdrawn or Postponed). The create function (0056) checked
-- nothing about the event's status, so a postponed event could take a venue straight back.
--
-- Both run under the event lock and recheck the latest assignment. event_postponements
-- keeps who postponed, why, when, and the date it came back with.

CREATE TABLE IF NOT EXISTS public.event_postponements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id) ON DELETE CASCADE,
    postponed_by text NOT NULL,
    previous_status text NOT NULL,
    reason text NOT NULL CHECK (btrim(reason) <> '' AND char_length(reason) <= 2000),
    postponed_at timestamptz NOT NULL DEFAULT now(),
    resumed_by text,
    resumed_at timestamptz,
    new_date_times timestamptz[]
);

CREATE UNIQUE INDEX IF NOT EXISTS event_postponements_one_open_idx
    ON public.event_postponements (event_request_id) WHERE resumed_at IS NULL;

ALTER TABLE public.event_postponements ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.event_postponements FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.event_postponements TO service_role;

CREATE OR REPLACE FUNCTION public.postpone_event_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id text,
    p_reason text
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
    v_reason text := pg_catalog.btrim(p_reason);
BEGIN
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;
    IF p_coordinator_id IS DISTINCT FROM (
        SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
        WHERE a.event_request_id = p_event_request_id ORDER BY a.id DESC LIMIT 1
    ) THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    IF v_event.status NOT IN ('Approved', 'Planning', 'Safety Review', 'Confirmed') THEN
        RAISE EXCEPTION 'transition not allowed from status %', v_event.status
            USING ERRCODE = 'P0004';
    END IF;
    IF v_reason IS NULL OR v_reason = '' OR pg_catalog.char_length(v_reason) > 2000 THEN
        RAISE EXCEPTION 'a reason of 1 to 2000 characters is required' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.event_postponements (event_request_id, postponed_by, previous_status, reason)
    VALUES (p_event_request_id, p_coordinator_id, v_event.status, v_reason);

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.postponement');
    UPDATE public.event_requests SET status = 'Postponed'
    WHERE id = p_event_request_id
    RETURNING * INTO v_event;
    RETURN v_event;
END;
$$;

CREATE OR REPLACE FUNCTION public.resume_postponed_event(
    p_event_request_id uuid,
    p_coordinator_id text,
    p_new_date_times timestamptz[]
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
BEGIN
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;
    IF p_coordinator_id IS DISTINCT FROM (
        SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
        WHERE a.event_request_id = p_event_request_id ORDER BY a.id DESC LIMIT 1
    ) THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    IF v_event.status <> 'Postponed' THEN
        RAISE EXCEPTION 'transition not allowed from status %', v_event.status
            USING ERRCODE = 'P0004';
    END IF;
    IF p_new_date_times IS NULL OR pg_catalog.cardinality(p_new_date_times) = 0
       OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(p_new_date_times) AS d
           WHERE d IS NULL OR d <= pg_catalog.clock_timestamp() OR NOT pg_catalog.isfinite(d)
       ) THEN
        RAISE EXCEPTION 'a new date in the future is required' USING ERRCODE = '22023';
    END IF;

    UPDATE public.event_postponements
    SET resumed_by = p_coordinator_id, resumed_at = pg_catalog.clock_timestamp(),
        new_date_times = p_new_date_times
    WHERE event_request_id = p_event_request_id AND resumed_at IS NULL;

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.resumed');
    UPDATE public.event_requests
    SET status = 'Planning', proposed_date_times = p_new_date_times
    WHERE id = p_event_request_id
    RETURNING * INTO v_event;
    RETURN v_event;
END;
$$;

REVOKE ALL ON FUNCTION public.postpone_event_by_coordinator(uuid, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.postpone_event_by_coordinator(uuid, text, text)
    TO service_role;
REVOKE ALL ON FUNCTION public.resume_postponed_event(uuid, text, timestamptz[])
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.resume_postponed_event(uuid, text, timestamptz[])
    TO service_role;

-- A postponed event stops holding venues and equipment (as 0073 does for a cancelled one).
CREATE OR REPLACE FUNCTION private.release_arrangements_on_event_postpone()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_actor uuid;
    v_reservation public.equipment_reservations;
BEGIN
    SELECT CASE WHEN coordinator_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                THEN coordinator_id::uuid END INTO v_actor
    FROM public.event_coordinator_assignments
    WHERE event_request_id = NEW.id
    ORDER BY id DESC LIMIT 1;

    UPDATE public.venue_booking_requests
    SET status = 'cancelled', cancelled_by = COALESCE(v_actor, requested_by), cancelled_at = now()
    WHERE event_request_id = NEW.id AND status IN ('pending', 'approved');

    UPDATE public.venue_holds
    SET status = 'released', closed_at = now(), closed_by = COALESCE(v_actor, placed_by)
    WHERE event_request_id = NEW.id AND status = 'active';

    FOR v_reservation IN
        SELECT * FROM public.equipment_reservations
        WHERE event_request_id = NEW.id
        ORDER BY id
        FOR UPDATE
    LOOP
        PERFORM private.release_reservation(v_reservation, v_actor, 'Event postponed');
    END LOOP;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.release_arrangements_on_event_postpone()
    FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS event_requests_release_arrangements_on_postpone ON public.event_requests;
CREATE TRIGGER event_requests_release_arrangements_on_postpone
    AFTER UPDATE OF status ON public.event_requests
    FOR EACH ROW
    WHEN (NEW.status = 'Postponed' AND OLD.status IS DISTINCT FROM 'Postponed')
    EXECUTE FUNCTION private.release_arrangements_on_event_postpone();

-- 0056's booking creation, unchanged except that an event which cannot use a venue is refused.
CREATE OR REPLACE FUNCTION public.create_event_venue_booking_request(p_booking jsonb, p_expected_event_updated_at timestamp with time zone)
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
    IF v_event.status IN ('Draft', 'Completed', 'Cancelled', 'Rejected', 'Withdrawn', 'Postponed') THEN
        RAISE EXCEPTION 'Event is not open for venue bookings' USING ERRCODE = 'P0004';
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
$function$;
