-- Venue booking conflict guard (SCRUM-20). Run once, after 0051.
--
-- private.check_booking_candidate is the one conflict check for a proposed
-- booking time: approval (below) and SCRUM-35's reschedule both call it. It
-- applies the venue's setup and turnaround (SCRUM-59): a booking occupies the
-- venue from start minus setup to end plus turnaround, and that padded range
-- must stay inside 07:00-24:00 (Product Owner, 20 October 2026). It returns
--   { "refusal_codes": [...], "conflicting_booking_ids": [...] }
-- with, in order, setup_outside_window, turnaround_outside_window and
-- booking_conflict. Empty refusal_codes means the time is clear.
--   * booking_conflict: an approved booking at the venue, not in
--     p_exclude_ids, shares a day and its padded time overlaps the candidate's.
--     Ranges are half-open, so a gap equal to setup plus turnaround is allowed.
--     Pending, rejected and cancelled bookings never conflict.
--   * p_exclude_ids: the bookings being moved, so their old times never block.
-- Blocks are not checked here (SCRUM-23/65); approval checks them as before.
--
-- The check takes no locks. A caller holds FOR UPDATE on the venue row first,
-- as decide_venue_booking_request and create_venue_block do, so two writers
-- for one venue run one at a time.
--
-- Errors: P0002 the venue does not exist; 22023 a missing argument or a time
-- that breaks 0050's rules (15-minute steps, 07:00-24:00, end after start, end
-- date on or after start date).
--
-- decide_venue_booking_request now refuses with the guard's codes, so the
-- refusal log accepts the two window codes. Lock order, the other codes,
-- errors and grants are unchanged.

ALTER TABLE public.venue_booking_refusals
    DROP CONSTRAINT venue_booking_refusals_codes_known,
    ADD CONSTRAINT venue_booking_refusals_codes_known
        CHECK (
            cardinality(refusal_codes) > 0
            AND refusal_codes <@ ARRAY[
                'venue_unavailable',
                'outside_operating_slots',
                'active_block',
                'setup_outside_window',
                'turnaround_outside_window',
                'booking_conflict'
            ]::text[]
        );

CREATE OR REPLACE FUNCTION private.check_booking_candidate(
    p_venue_id uuid,
    p_start_date date,
    p_end_date date,
    p_start_minute integer,
    p_end_minute integer,
    p_exclude_ids uuid[] DEFAULT '{}'
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_setup integer;
    v_turnaround integer;
    v_codes text[] := '{}';
    v_bookings uuid[];
BEGIN
    IF p_venue_id IS NULL OR p_start_date IS NULL OR p_end_date IS NULL
       OR p_start_minute IS NULL OR p_end_minute IS NULL THEN
        RAISE EXCEPTION 'a candidate needs a venue, dates and times' USING ERRCODE = '22023';
    END IF;
    IF p_end_date < p_start_date
       OR p_start_minute % 15 <> 0 OR p_end_minute % 15 <> 0
       OR p_start_minute < 420 OR p_end_minute > 1440
       OR p_end_minute <= p_start_minute THEN
        RAISE EXCEPTION 'candidate time breaks the booking time rules' USING ERRCODE = '22023';
    END IF;

    SELECT v.setup_minutes, v.turnaround_minutes INTO v_setup, v_turnaround
    FROM public.venues AS v
    WHERE v.id = p_venue_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'venue not found' USING ERRCODE = 'P0002';
    END IF;

    IF p_start_minute - v_setup < 420 THEN
        v_codes := v_codes || 'setup_outside_window'::text;
    END IF;
    IF p_end_minute + v_turnaround > 1440 THEN
        v_codes := v_codes || 'turnaround_outside_window'::text;
    END IF;

    -- Same venue, so both ranges carry the same padding.
    SELECT COALESCE(array_agg(o.id ORDER BY o.start_date, o.start_minute, o.id), '{}')
    INTO v_bookings
    FROM public.venue_booking_requests AS o
    WHERE o.venue_id = p_venue_id
      AND o.status = 'approved'
      AND o.id <> ALL (COALESCE(p_exclude_ids, '{}'))
      AND o.start_date <= p_end_date
      AND p_start_date <= o.end_date
      AND o.start_minute - v_setup < p_end_minute + v_turnaround
      AND p_start_minute - v_setup < o.end_minute + v_turnaround;
    IF cardinality(v_bookings) > 0 THEN
        v_codes := v_codes || 'booking_conflict'::text;
    END IF;

    RETURN jsonb_build_object(
        'refusal_codes', to_jsonb(v_codes),
        'conflicting_booking_ids', to_jsonb(v_bookings)
    );
END;
$$;

REVOKE ALL ON FUNCTION private.check_booking_candidate(
    uuid, date, date, integer, integer, uuid[]
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.check_booking_candidate(
    uuid, date, date, integer, integer, uuid[]
) TO service_role;

-- Unchanged from 0051 except the booking check, which is now the guard.
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
    v_guard jsonb;
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

    -- SCRUM-20: setup and turnaround padding, excluding the request itself.
    v_guard := private.check_booking_candidate(
        v_venue_id, v_request.start_date, v_request.end_date,
        v_request.start_minute, v_request.end_minute, ARRAY[v_request.id]
    );
    v_codes := v_codes || ARRAY(SELECT jsonb_array_elements_text(v_guard -> 'refusal_codes'));
    v_bookings := ARRAY(
        SELECT jsonb_array_elements_text(v_guard -> 'conflicting_booking_ids')::uuid
    );

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
