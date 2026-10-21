-- Run after 0051_venue_block_times.sql (SCRUM-65 slice 2). Every change is
-- rolled back. Uses no DELETE or UPDATE. Borrows the oldest auth user, which
-- venue_blocks.created_by needs.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_venue_block_times.sql

BEGIN;

DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
    v_day date := current_date + 40;
    v_venue uuid;
    v_block public.venue_blocks%ROWTYPE;
    v_id uuid;
    v_result jsonb;
    v_count int;
BEGIN
    -- AC5-H2: every existing block holds its slots' range.
    SELECT count(*) INTO v_count
    FROM public.venue_blocks AS b
    CROSS JOIN LATERAL private.booking_slots_range(b.slots) AS t
    WHERE (b.start_minute, b.end_minute) <> (t.start_minute, t.end_minute);
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC5-H2: % blocks do not match their slots', v_count;
    END IF;

    -- AC5-N2: non-consecutive block slots would stop the migration (none are left).
    IF EXISTS (SELECT 1 FROM public.venue_blocks AS b
               WHERE 'AM' = ANY (b.slots) AND 'NIGHT' = ANY (b.slots) AND NOT ('PM' = ANY (b.slots))) THEN
        RAISE EXCEPTION 'AC5-N2: a non-consecutive block exists';
    END IF;

    -- A venue with only AM operating: the old operating-slot check is retired.
    INSERT INTO public.venues (name, location, max_capacity, facilities,
            accessibility_features, supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM65 block venue', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM']::public.booking_slot[])
        RETURNING id INTO v_venue;

    -- AC3-H1: a block takes its times and gets the slots they touch.
    SELECT * INTO v_block FROM public.create_venue_block(
        v_venue, v_day, v_day, 750, 840, 'maintenance', '  Repairs  ', v_user);
    IF (v_block.start_minute, v_block.end_minute) <> (750, 840) OR v_block.slots <> '{PM}'
       OR v_block.reason_detail <> 'Repairs' THEN
        RAISE EXCEPTION 'AC3-H1: block stored as %', to_jsonb(v_block);
    END IF;

    -- AC3-N1: the database refuses bad block times from any caller.
    BEGIN
        PERFORM public.create_venue_block(v_venue, v_day, v_day, 730, 840, 'safety', NULL, v_user);
        RAISE EXCEPTION 'AC3-N1: off-step block accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        PERFORM public.create_venue_block(v_venue, v_day, v_day, 840, 840, 'safety', NULL, v_user);
        RAISE EXCEPTION 'AC3-N1: empty block accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- AC3-B1: one step of overlap is refused; ending at the block's start is allowed.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day, v_day, 660, 765)
        RETURNING id INTO v_id;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->'refusal_codes' <> '["active_block"]'::jsonb
       OR NOT (v_result->'conflicting_block_ids' @> to_jsonb(ARRAY[v_block.id])) THEN
        RAISE EXCEPTION 'AC3-B1: overlap not refused: %', v_result;
    END IF;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day, v_day, 660, 750)
        RETURNING id INTO v_id;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->>'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC3-B1: adjacent booking refused: %', v_result;
    END IF;

    -- AC4-P3: a PM-time booking at an AM-only venue approves (fixed 07:00-24:00 window).
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 1, v_day + 1, 1080, 1200)
        RETURNING id INTO v_id;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->>'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC4-P3: operating slots still refuse: %', v_result;
    END IF;

    -- DB-1: browser roles cannot create blocks.
    IF has_function_privilege('anon',
           'public.create_venue_block(uuid, date, date, integer, integer, public.block_reason, text, uuid)', 'EXECUTE')
       OR has_function_privilege('authenticated',
           'public.create_venue_block(uuid, date, date, integer, integer, public.block_reason, text, uuid)', 'EXECUTE')
       OR NOT has_function_privilege('service_role',
           'public.create_venue_block(uuid, date, date, integer, integer, public.block_reason, text, uuid)', 'EXECUTE') THEN
        RAISE EXCEPTION 'DB-1: create_venue_block grants are wrong';
    END IF;

    RAISE NOTICE 'ALL SCRUM-65 BLOCK TIME VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
