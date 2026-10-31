-- Venue replacement requests (SCRUM-63 AC4, AC5). Run once, after 0064 and 0066.
--
-- When a venue block flags an approved booking (0064), the event's coordinator can
-- ask for a replacement at another venue. The replacement is an ordinary pending
-- booking request for the same event, dates and times, linked to the flagged
-- booking by venue_booking_requests.replaces_booking_id. Venue Staff decide it as
-- usual (suitability, blocks and the conflict guard of 0054 all apply).
--
--   * create_replacement_venue_booking_request(replaces, new_id, venue, requested_by,
--     expected_event_updated_at) checks that the booking exists, is approved, has an
--     open 'venue_block' flag and is not at the chosen venue, then stores the request
--     through 0056's versioned creator (venue and event locks, assigned coordinator,
--     event version) and links it. The booking is locked after the creator and checked
--     again, so a booking cancelled in the meantime is refused. At most one pending or
--     approved replacement exists per booking (a partial unique index).
--     Errors: P0002 booking or venue not found; P0003 caller is not the event's
--     coordinator; P0004 booking not approved, booking not flagged, or event changed;
--     22023 same venue; 23505 a replacement is already active.
--   * decide_venue_booking_request (0066, which keeps 0054's guard and adds SCRUM-18's
--     hold handling) is unchanged except the end of the approval
--     path: when the approved request replaces a booking, that booking is cancelled
--     (by the approver, only if it is still approved) and its open 'venue_block' flags
--     are cleared with 0032's clear_arrangement_review, in the same transaction. A
--     rejected or cancelled replacement changes neither the old booking nor its flag.
--
-- Locks: venue row, then the request row (as before), then the replaced booking last.
-- cancel_venue_booking_request locks only its own row, so no cycle is possible.
-- Run only once venueService can send replaces_booking_id (it ignores the column
-- until then). Verify with verify_venue_replacement_requests.sql.

ALTER TABLE public.venue_booking_requests
    ADD COLUMN IF NOT EXISTS replaces_booking_id uuid
        REFERENCES public.venue_booking_requests (id);

ALTER TABLE public.venue_booking_requests
    DROP CONSTRAINT IF EXISTS venue_booking_requests_replaces_other;
ALTER TABLE public.venue_booking_requests
    ADD CONSTRAINT venue_booking_requests_replaces_other
    CHECK (replaces_booking_id IS NULL OR replaces_booking_id <> id);

CREATE UNIQUE INDEX IF NOT EXISTS venue_booking_replacement_active_idx
    ON public.venue_booking_requests (replaces_booking_id)
    WHERE replaces_booking_id IS NOT NULL AND status IN ('pending', 'approved');

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
    v_new := public.create_event_venue_booking_request(
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
        p_expected_event_updated_at
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

-- Unchanged from 0054 except the replacement step at the end of the approval path.
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
    v_holds uuid[];
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
        -- SCRUM-18: a rejected conversion ends its hold. An expired hold is left to
        -- the sweep, which marks it expired and sends its notice.
        UPDATE public.venue_holds AS h
        SET status = 'released', closed_at = now(), closed_by = p_decided_by
        WHERE h.booking_request_id = v_request.id AND h.status = 'active'
          AND h.expires_at > now();
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
    v_holds := ARRAY(
        SELECT jsonb_array_elements_text(v_guard -> 'conflicting_hold_ids')::uuid
    );

    IF cardinality(v_codes) > 0 THEN
        INSERT INTO public.venue_booking_refusals (
            booking_request_id, refused_by, refusal_codes,
            conflicting_block_ids, conflicting_booking_ids, conflicting_hold_ids
        )
        VALUES (p_booking_request_id, p_decided_by, v_codes, v_blocks, v_bookings, v_holds);
        RETURN jsonb_build_object(
            'outcome', 'refused',
            'refusal_codes', to_jsonb(v_codes),
            'conflicting_block_ids', to_jsonb(v_blocks),
            'conflicting_booking_ids', to_jsonb(v_bookings),
            'conflicting_hold_ids', to_jsonb(v_holds),
            'booking', to_jsonb(v_request)
        );
    END IF;

    UPDATE public.venue_booking_requests AS r
    SET status = 'approved',
        decided_by = p_decided_by,
        decided_at = now()
    WHERE r.id = p_booking_request_id
    RETURNING * INTO v_request;
    -- SCRUM-18: an approved conversion becomes the booking, so its hold ends. An
    -- expired hold is never converted; the sweep marks it expired.
    UPDATE public.venue_holds AS h
    SET status = 'converted', closed_at = now(), closed_by = p_decided_by
    WHERE h.booking_request_id = v_request.id AND h.status = 'active'
      AND h.expires_at > now();

    -- SCRUM-63 AC5: an approved replacement cancels the booking it replaces and clears
    -- that booking's venue-block flags, in this transaction. An original that is no
    -- longer approved (the coordinator cancelled it first) is left as it is.
    IF v_request.replaces_booking_id IS NOT NULL THEN
        UPDATE public.venue_booking_requests AS o
        SET status = 'cancelled',
            cancelled_by = p_decided_by,
            cancelled_at = now()
        WHERE o.id = v_request.replaces_booking_id
          AND o.status = 'approved';
        PERFORM public.clear_arrangement_review(ar.id, p_decided_by, ARRAY['venue_booking'])
        FROM public.arrangement_reviews AS ar
        WHERE ar.arrangement = 'venue_booking'
          AND ar.arrangement_id = v_request.replaces_booking_id
          AND ar.trigger_type = 'venue_block'
          AND ar.cleared_at IS NULL;
    END IF;

    RETURN jsonb_build_object('outcome', 'approved', 'booking', to_jsonb(v_request));
END;
$$;
