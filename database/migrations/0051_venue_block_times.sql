-- Venue block times in 15-minute steps (SCRUM-65 slice 2). Run once, after 0050.
--
-- A block keeps its inclusive date range and gains one start and end time
-- that apply on each date, in minutes after midnight, Singapore local time,
-- with the same checks as bookings (0050). Existing blocks convert from their
-- slots with 0050's ranges (AM 07:00-12:00, PM 12:00-18:00, NIGHT
-- 18:00-24:00); a block whose slots are not consecutive stops the migration
-- with its id. Ids, dates, statuses and reasons are unchanged.
--
-- slots stays, set by 0050's trigger to the slots the time touches, for
-- SCRUM-31's calendar until it moves to times.
--
-- create_venue_block takes the times instead of slots (same venue lock).
-- decide_venue_booking_request compares blocks by time too, and no longer
-- refuses on the venue's operating slots: every venue operates 07:00-24:00
-- (Product Owner, 20 October 2026), which the time checks already enforce.
-- Lock order, the remaining refusal codes and errors are unchanged.

DO $$
DECLARE
    v_ids text;
BEGIN
    SELECT string_agg(b.id::text, ', ' ORDER BY b.id) INTO v_ids
    FROM public.venue_blocks AS b
    WHERE 'AM' = ANY (b.slots) AND 'NIGHT' = ANY (b.slots) AND NOT ('PM' = ANY (b.slots));
    IF v_ids IS NOT NULL THEN
        RAISE EXCEPTION 'blocks with non-consecutive slots need a manual decision: %', v_ids;
    END IF;
END;
$$;

ALTER TABLE public.venue_blocks
    ADD COLUMN start_minute integer,
    ADD COLUMN end_minute integer;

UPDATE public.venue_blocks AS b
SET (start_minute, end_minute) =
    (SELECT t.start_minute, t.end_minute FROM private.booking_slots_range(b.slots) AS t);

ALTER TABLE public.venue_blocks
    ALTER COLUMN start_minute SET NOT NULL,
    ALTER COLUMN end_minute SET NOT NULL,
    ADD CONSTRAINT venue_blocks_times_valid CHECK (
        start_minute % 15 = 0 AND end_minute % 15 = 0
        AND start_minute >= 420 AND end_minute <= 1440
        AND end_minute > start_minute
    );

-- 0050's trigger function only reads start_minute, end_minute and slots.
CREATE TRIGGER set_block_time_slots
    BEFORE INSERT OR UPDATE OF start_minute, end_minute
    ON public.venue_blocks
    FOR EACH ROW EXECUTE FUNCTION private.set_booking_time_slots();

DROP FUNCTION public.create_venue_block(
    uuid, date, date, public.booking_slot[], public.block_reason, text, uuid
);

CREATE FUNCTION public.create_venue_block(
    p_venue_id uuid,
    p_start_date date,
    p_end_date date,
    p_start_minute integer,
    p_end_minute integer,
    p_reason_category public.block_reason,
    p_reason_detail text,
    p_created_by uuid
)
RETURNS public.venue_blocks
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_block public.venue_blocks%ROWTYPE;
BEGIN
    PERFORM 1 FROM public.venues AS v WHERE v.id = p_venue_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'venue not found' USING ERRCODE = 'P0002';
    END IF;
    INSERT INTO public.venue_blocks (
        venue_id, start_date, end_date, start_minute, end_minute,
        reason_category, reason_detail, created_by
    )
    VALUES (
        p_venue_id, p_start_date, p_end_date, p_start_minute, p_end_minute,
        p_reason_category, NULLIF(btrim(p_reason_detail), ''), p_created_by
    )
    RETURNING * INTO v_block;
    RETURN v_block;
END;
$$;

REVOKE ALL ON FUNCTION public.create_venue_block(
    uuid, date, date, integer, integer, public.block_reason, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_venue_block(
    uuid, date, date, integer, integer, public.block_reason, text, uuid
) TO service_role;

-- Unchanged from 0050 except the block query and the removed operating-slot check.
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

    -- SCRUM-65: a shared day and overlapping half-open time ranges.
    SELECT COALESCE(array_agg(b.id ORDER BY b.id), '{}') INTO v_blocks
    FROM public.venue_blocks AS b
    WHERE b.venue_id = v_venue_id
      AND b.status = 'active'
      AND b.start_date <= v_request.end_date
      AND v_request.start_date <= b.end_date
      AND b.start_minute < v_request.end_minute
      AND v_request.start_minute < b.end_minute;
    IF cardinality(v_blocks) > 0 THEN
        v_codes := v_codes || 'active_block'::text;
    END IF;

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
