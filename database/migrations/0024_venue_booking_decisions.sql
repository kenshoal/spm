-- Venue booking decisions (SCRUM-15). Safe to re-run.
--
-- decide_venue_booking_request approves or rejects a pending request in one
-- transaction. It locks the venues row first, then the request row, so two
-- approvals for one venue, or an approval and a new block, run one at a time
-- (as agreed in 0018). Approval re-checks, at decision time:
--   * venue_unavailable:       the venue's catalogue status is not 'available'
--   * outside_operating_slots: a requested slot is not an operating slot
--   * active_block:            an active block shares a date and a slot
--   * booking_conflict:        another approved request shares a date and a slot
-- Dates are inclusive; NIGHT belongs to its starting date. Pending and rejected
-- requests never conflict. A refused approval leaves the request pending and
-- writes one venue_booking_refusals row, so the reason is recorded (AC5).
--
-- create_venue_block takes the same venues lock before inserting a block.
--
-- Errors: P0002 the request or venue does not exist; 55000 the request is
-- no longer pending; 22023 an invalid decision (unknown value, a rejection without
-- a reason, or an approval with a reason or alternative).
--
-- venueService calls both functions with the server-side secret key. Browser
-- roles cannot execute them or read the refusal log.

CREATE TABLE IF NOT EXISTS public.venue_booking_refusals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_request_id uuid NOT NULL
        REFERENCES public.venue_booking_requests (id) ON DELETE RESTRICT,
    refused_by uuid NOT NULL,
    refusal_codes text[] NOT NULL,
    conflicting_block_ids uuid[] NOT NULL DEFAULT '{}',
    conflicting_booking_ids uuid[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT venue_booking_refusals_codes_known
        CHECK (
            cardinality(refusal_codes) > 0
            AND refusal_codes <@ ARRAY[
                'venue_unavailable',
                'outside_operating_slots',
                'active_block',
                'booking_conflict'
            ]::text[]
        )
);

-- A request's refusals, oldest first.
CREATE INDEX IF NOT EXISTS venue_booking_refusals_request_idx
    ON public.venue_booking_refusals (booking_request_id, created_at, id);

ALTER TABLE public.venue_booking_refusals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.venue_booking_refusals FROM anon, authenticated;
GRANT SELECT, INSERT ON public.venue_booking_refusals TO service_role;

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

    SELECT COALESCE(array_agg(o.id ORDER BY o.id), '{}') INTO v_bookings
    FROM public.venue_booking_requests AS o
    WHERE o.venue_id = v_venue_id
      AND o.status = 'approved'
      AND o.id <> v_request.id
      AND o.start_date <= v_request.end_date
      AND v_request.start_date <= o.end_date
      AND o.slots && v_request.slots;
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

CREATE OR REPLACE FUNCTION public.create_venue_block(
    p_venue_id uuid,
    p_start_date date,
    p_end_date date,
    p_slots public.booking_slot[],
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
        venue_id, start_date, end_date, slots, reason_category, reason_detail, created_by
    )
    VALUES (
        p_venue_id, p_start_date, p_end_date, p_slots, p_reason_category,
        NULLIF(btrim(p_reason_detail), ''), p_created_by
    )
    RETURNING * INTO v_block;
    RETURN v_block;
END;
$$;

REVOKE ALL ON FUNCTION public.decide_venue_booking_request(uuid, text, uuid, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.decide_venue_booking_request(uuid, text, uuid, text, text)
    TO service_role;

REVOKE ALL ON FUNCTION public.create_venue_block(
    uuid, date, date, public.booking_slot[], public.block_reason, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_venue_block(
    uuid, date, date, public.booking_slot[], public.block_reason, text, uuid
) TO service_role;
