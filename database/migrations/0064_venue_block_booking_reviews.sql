-- Venue block booking reviews (SCRUM-63 AC1, AC2). Run once, after 0059, and only
-- once the readers that accept 'venue_block' are deployed (the eventRequestService
-- response model and the frontend cause label), as 0055 required for
-- 'venue_timing_change'.
--
-- public.create_venue_block now also flags the bookings the new block affects in
-- arrangement_reviews (arrangement 'venue_booking', trigger_type 'venue_block',
-- trigger_id = the block's id), in the same transaction as the block. 0037's
-- trigger queues the existing arrangement_needs_review notice for each flag and
-- 0038 delivers it to the event's coordinator and Venue Staff with no
-- change_request_id. If any step fails, neither the block nor any flag is saved.
--
-- Affected bookings (SCRUM-63 AC1, assumptions A1 and A2):
--   * approved bookings at the blocked venue whose end_date is on or after today
--     in Singapore, taken once per transaction;
--   * that share at least one date with the block and overlap it in time. Time is
--     half-open, so a booking that ends where the block starts is not affected;
--   * whose event is not Draft, Completed, Cancelled or Rejected (0033's rule).
-- Pending, rejected and cancelled bookings are never flagged; approval already
-- refuses a pending booking onto a block with active_block. A booking whose event
-- does not exist (venue_booking_requests.event_request_id has no foreign key)
-- cannot carry a review, so it is skipped and the block is still saved.
--
-- No booking, approval, event status or notification setting changes. The return
-- type and arguments of create_venue_block are unchanged (0051), so venueService
-- needs no change to call it. The function becomes SECURITY DEFINER because
-- arrangement_reviews is SELECT-only for service_role (0030); like
-- update_venue_timing it stays executable by service_role only.
--
-- Locks: the venue row FOR UPDATE first (the same lock as approval, 0054 and
-- update_venue_timing), then event rows only through the foreign-key insert into
-- arrangement_reviews (0039 protocol).

ALTER TABLE public.arrangement_reviews
    DROP CONSTRAINT arrangement_reviews_trigger_type_check,
    ADD CONSTRAINT arrangement_reviews_trigger_type_check
        CHECK (trigger_type IN (
            'event_change', 'equipment_unavailable', 'safety_recheck',
            'venue_timing_change', 'venue_block'
        ));

CREATE OR REPLACE FUNCTION public.create_venue_block(
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
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_venue public.venues%ROWTYPE;
    v_block public.venue_blocks%ROWTYPE;
    v_today date := (pg_catalog.transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
BEGIN
    SELECT * INTO v_venue FROM public.venues AS v WHERE v.id = p_venue_id FOR UPDATE;
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

    INSERT INTO public.arrangement_reviews
        (event_request_id, arrangement, arrangement_id, trigger_id,
         trigger_type, changed_fields, reason)
    SELECT b.event_request_id, 'venue_booking', b.id, v_block.id,
           'venue_block', '{}',
           pg_catalog.format(
               'Venue %s is blocked from %s to %s, %s to %s; this booking needs a new venue.',
               v_venue.name, v_block.start_date, v_block.end_date,
               pg_catalog.format('%s:%s',
                   pg_catalog.lpad((v_block.start_minute / 60)::text, 2, '0'),
                   pg_catalog.lpad((v_block.start_minute % 60)::text, 2, '0')),
               pg_catalog.format('%s:%s',
                   pg_catalog.lpad((v_block.end_minute / 60)::text, 2, '0'),
                   pg_catalog.lpad((v_block.end_minute % 60)::text, 2, '0')))
    FROM public.venue_booking_requests AS b
    JOIN public.event_requests AS e ON e.id = b.event_request_id
    WHERE b.venue_id = p_venue_id
      AND b.status = 'approved'
      AND b.end_date >= v_today
      AND b.start_date <= v_block.end_date
      AND v_block.start_date <= b.end_date
      AND b.start_minute < v_block.end_minute
      AND v_block.start_minute < b.end_minute
      AND e.status NOT IN ('Draft', 'Completed', 'Cancelled', 'Rejected')
    ON CONFLICT ON CONSTRAINT arrangement_reviews_trigger_target_unique DO NOTHING;

    RETURN v_block;
END;
$$;

REVOKE ALL ON FUNCTION public.create_venue_block(
    uuid, date, date, integer, integer, public.block_reason, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_venue_block(
    uuid, date, date, integer, integer, public.block_reason, text, uuid
) TO service_role;
