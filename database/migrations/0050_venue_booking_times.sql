-- Venue booking times in 15-minute steps (SCRUM-65 slice 1). Run once, after 0042.
--
-- A booking keeps its inclusive date range and gains one start and end time
-- that apply on each date, in minutes after midnight, Singapore local time
-- (07:00 = 420, 24:00 = 1440). The database enforces the 15-minute step, the
-- 07:00-24:00 window and end after start.
--
-- Conversion (Product Owner, 20 October 2026): AM = 07:00-12:00,
-- PM = 12:00-18:00, NIGHT = 18:00-24:00. Consecutive slots join into one range.
-- A booking whose slots are not consecutive (AM and NIGHT without PM) stops
-- the migration with its id, so nothing is guessed. Ids, dates, statuses and
-- links are unchanged.
--
-- Until Sprint 4, slots is kept for slot-based readers: a trigger sets it to
-- the slots the time range touches (11:00-13:00 -> AM, PM). An insert that
-- still sends only slots gets their range. Blocks stay whole-slot until
-- Sprint 4, so comparing a booking's touched slots with a block is exact.
--
-- decide_venue_booking_request (0024) now compares approved bookings by time:
-- the date ranges share a day and the half-open time ranges overlap. SCRUM-20
-- adds the venue's setup and turnaround padding inside the same check. Lock
-- order, refusal codes and errors are unchanged.

CREATE OR REPLACE FUNCTION private.booking_slots_range(
    p_slots public.booking_slot[],
    OUT start_minute integer,
    OUT end_minute integer
)
LANGUAGE plpgsql
IMMUTABLE
SET search_path = ''
AS $$
DECLARE
    v_covered integer;
BEGIN
    SELECT min(t.a), max(t.b), sum(t.b - t.a)
    INTO start_minute, end_minute, v_covered
    FROM (VALUES ('AM'::public.booking_slot, 420, 720),
                 ('PM'::public.booking_slot, 720, 1080),
                 ('NIGHT'::public.booking_slot, 1080, 1440)) AS t(s, a, b)
    WHERE t.s = ANY (p_slots);
    IF v_covered IS NULL OR v_covered <> end_minute - start_minute THEN
        RAISE EXCEPTION 'slots % are not consecutive', p_slots USING ERRCODE = '22023';
    END IF;
END;
$$;

-- AC5-N1: refuse to convert rather than guess.
DO $$
DECLARE
    v_ids text;
BEGIN
    SELECT string_agg(r.id::text, ', ' ORDER BY r.id) INTO v_ids
    FROM public.venue_booking_requests AS r
    WHERE 'AM' = ANY (r.slots) AND 'NIGHT' = ANY (r.slots) AND NOT ('PM' = ANY (r.slots));
    IF v_ids IS NOT NULL THEN
        RAISE EXCEPTION 'bookings with non-consecutive slots need a manual decision: %', v_ids;
    END IF;
END;
$$;

ALTER TABLE public.venue_booking_requests
    ADD COLUMN start_minute integer,
    ADD COLUMN end_minute integer;

UPDATE public.venue_booking_requests AS r
SET (start_minute, end_minute) =
    (SELECT t.start_minute, t.end_minute FROM private.booking_slots_range(r.slots) AS t);

ALTER TABLE public.venue_booking_requests
    ALTER COLUMN start_minute SET NOT NULL,
    ALTER COLUMN end_minute SET NOT NULL,
    ADD CONSTRAINT venue_booking_requests_times_valid CHECK (
        start_minute % 15 = 0 AND end_minute % 15 = 0
        AND start_minute >= 420 AND end_minute <= 1440
        AND end_minute > start_minute
    );

CREATE OR REPLACE FUNCTION private.set_booking_time_slots()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF NEW.start_minute IS NULL AND NEW.end_minute IS NULL THEN
        SELECT t.start_minute, t.end_minute INTO NEW.start_minute, NEW.end_minute
        FROM private.booking_slots_range(NEW.slots) AS t;
    END IF;
    -- Left NULL or invalid, the NOT NULL and CHECK constraints refuse the row.
    NEW.slots := ARRAY(
        SELECT t.s
        FROM (VALUES ('AM'::public.booking_slot, 420, 720),
                     ('PM'::public.booking_slot, 720, 1080),
                     ('NIGHT'::public.booking_slot, 1080, 1440)) AS t(s, a, b)
        WHERE NEW.start_minute < t.b AND t.a < NEW.end_minute
        ORDER BY t.a
    );
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.booking_slots_range(public.booking_slot[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.set_booking_time_slots() FROM PUBLIC;

CREATE TRIGGER set_booking_time_slots
    BEFORE INSERT OR UPDATE OF start_minute, end_minute
    ON public.venue_booking_requests
    FOR EACH ROW EXECUTE FUNCTION private.set_booking_time_slots();

-- Unchanged from 0024 except the booking_conflict query.
CREATE OR REPLACE FUNCTION public.decide_venue_booking_request(
    p_booking_request_id uuid,
    p_decision text,
    p_decided_by uuid,
    p_decision_reason text DEFAULT NULL,
    p_suggested_alternative text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_venue_id uuid;
    v_venue public.venues%ROWTYPE;
    v_request public.venue_booking_requests%ROWTYPE;
    v_reason text := NULLIF(btrim(p_decision_reason), '');
    v_alternative text := NULLIF(btrim(p_suggested_alternative), '');
    v_codes text[] := '{}';
    v_blocks uuid[];
    v_bookings uuid[];
BEGIN
    IF p_decision IS NULL OR p_decision NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'decision must be approved or rejected' USING ERRCODE = '22023';
    END IF;
    IF p_decision = 'rejected' AND v_reason IS NULL THEN
        RAISE EXCEPTION 'a rejection needs a reason' USING ERRCODE = '22023';
    END IF;
    IF p_decision = 'approved' AND (v_reason IS NOT NULL OR v_alternative IS NOT NULL) THEN
        RAISE EXCEPTION 'an approval carries no reason or alternative' USING ERRCODE = '22023';
    END IF;

    SELECT r.venue_id INTO v_venue_id
    FROM public.venue_booking_requests AS r
    WHERE r.id = p_booking_request_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'booking request not found' USING ERRCODE = 'P0002';
    END IF;

    -- Venue first, then the request: the same order as create_venue_block.
    SELECT * INTO v_venue FROM public.venues AS v WHERE v.id = v_venue_id FOR UPDATE;
    SELECT * INTO v_request
    FROM public.venue_booking_requests AS r
    WHERE r.id = p_booking_request_id
    FOR UPDATE;

    IF v_request.status <> 'pending' THEN
        RAISE EXCEPTION 'booking request has already been decided' USING ERRCODE = '55000';
    END IF;

    IF p_decision = 'rejected' THEN
        UPDATE public.venue_booking_requests AS r
        SET status = 'rejected',
            decision_reason = v_reason,
            suggested_alternative = v_alternative,
            decided_by = p_decided_by,
            decided_at = now()
        WHERE r.id = p_booking_request_id
        RETURNING * INTO v_request;
        RETURN jsonb_build_object('outcome', 'rejected', 'booking', to_jsonb(v_request));
    END IF;

    IF v_venue.status <> 'available' THEN
        v_codes := v_codes || 'venue_unavailable'::text;
    END IF;
    IF NOT (v_request.slots <@ v_venue.operating_slots) THEN
        v_codes := v_codes || 'outside_operating_slots'::text;
    END IF;

    -- Blocks are whole slots until Sprint 4, so the touched slots are exact.
    SELECT COALESCE(array_agg(b.id ORDER BY b.id), '{}') INTO v_blocks
    FROM public.venue_blocks AS b
    WHERE b.venue_id = v_venue_id
      AND b.status = 'active'
      AND b.start_date <= v_request.end_date
      AND v_request.start_date <= b.end_date
      AND b.slots && v_request.slots;
    IF cardinality(v_blocks) > 0 THEN
        v_codes := v_codes || 'active_block'::text;
    END IF;

    -- SCRUM-65: a shared day and overlapping half-open time ranges.
    SELECT COALESCE(array_agg(o.id ORDER BY o.id), '{}') INTO v_bookings
    FROM public.venue_booking_requests AS o
    WHERE o.venue_id = v_venue_id
      AND o.status = 'approved'
      AND o.id <> v_request.id
      AND o.start_date <= v_request.end_date
      AND v_request.start_date <= o.end_date
      AND o.start_minute < v_request.end_minute
      AND v_request.start_minute < o.end_minute;
    IF cardinality(v_bookings) > 0 THEN
        v_codes := v_codes || 'booking_conflict'::text;
    END IF;

    IF cardinality(v_codes) > 0 THEN
        INSERT INTO public.venue_booking_refusals (
            booking_request_id, refused_by, refusal_codes,
            conflicting_block_ids, conflicting_booking_ids
        )
        VALUES (p_booking_request_id, p_decided_by, v_codes, v_blocks, v_bookings);
        RETURN jsonb_build_object(
            'outcome', 'refused',
            'refusal_codes', to_jsonb(v_codes),
            'conflicting_block_ids', to_jsonb(v_blocks),
            'conflicting_booking_ids', to_jsonb(v_bookings),
            'booking', to_jsonb(v_request)
        );
    END IF;

    UPDATE public.venue_booking_requests AS r
    SET status = 'approved',
        decided_by = p_decided_by,
        decided_at = now()
    WHERE r.id = p_booking_request_id
    RETURNING * INTO v_request;
    RETURN jsonb_build_object('outcome', 'approved', 'booking', to_jsonb(v_request));
END;
$$;
