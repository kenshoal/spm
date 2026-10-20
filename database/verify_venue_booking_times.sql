-- Run after 0050_venue_booking_times.sql and 0051_venue_block_times.sql (SCRUM-65). Every change is
-- rolled back. Uses no DELETE or UPDATE. Borrows the oldest auth user, which
-- venue_blocks.created_by needs.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_venue_booking_times.sql

BEGIN;

DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
    v_day date := current_date + 30;
    v_venue uuid;
    v_id uuid;
    v_first uuid;
    v_row public.venue_booking_requests%ROWTYPE;
    v_result jsonb;
    v_bad record;
    v_count int;
BEGIN
    -- AC5-H1: every existing booking holds its slots' range, and its slots are
    -- exactly the slots that range touches.
    SELECT count(*) INTO v_count
    FROM public.venue_booking_requests AS r
    CROSS JOIN LATERAL private.booking_slots_range(r.slots) AS t
    WHERE (r.start_minute, r.end_minute) <> (t.start_minute, t.end_minute);
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC5-H1: % bookings do not match their slots', v_count;
    END IF;
    IF (SELECT (t.start_minute, t.end_minute)::text
        FROM private.booking_slots_range('{PM,AM}') AS t) <> '(420,1080)'
       OR (SELECT (t.start_minute, t.end_minute)::text
           FROM private.booking_slots_range('{NIGHT}') AS t) <> '(1080,1440)' THEN
        RAISE EXCEPTION 'AC5-H1: wrong slot ranges';
    END IF;

    -- AC5-N1: non-consecutive slots are refused.
    BEGIN
        PERFORM private.booking_slots_range('{AM,NIGHT}');
        RAISE EXCEPTION 'AC5-N1: AM+NIGHT converted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;

    INSERT INTO public.venues (name, location, max_capacity, facilities,
            accessibility_features, supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM65 venue', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
        RETURNING id INTO v_venue;

    -- AC1-X1: the database refuses bad times from any caller.
    FOR v_bad IN
        SELECT * FROM (VALUES ('off step', 610, 720), ('before 07:00', 405, 480),
                              ('after 24:00', 1380, 1455), ('empty', 720, 720)) AS t(label, s, e)
    LOOP
        BEGIN
            INSERT INTO public.venue_booking_requests (venue_id, requested_by,
                    event_request_id, start_date, end_date, start_minute, end_minute)
                VALUES (v_venue, v_user, gen_random_uuid(), v_day, v_day, v_bad.s, v_bad.e);
            RAISE EXCEPTION 'AC1-X1 %: accepted', v_bad.label;
        EXCEPTION WHEN check_violation THEN NULL;
        END;
    END LOOP;

    -- AC1-X1 / AC1-P1: a valid time gets its touched slots; slots alone get their range.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day, v_day, 660, 780)
        RETURNING * INTO v_row;
    IF v_row.slots <> '{AM,PM}' THEN
        RAISE EXCEPTION 'AC1-P1: 11:00-13:00 got slots %', v_row.slots;
    END IF;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 1, v_day + 1, '{PM}')
        RETURNING * INTO v_row;
    IF (v_row.start_minute, v_row.end_minute) <> (720, 1080) THEN
        RAISE EXCEPTION 'AC5-H1: PM-only insert got % to %', v_row.start_minute, v_row.end_minute;
    END IF;

    -- AC2: an approved 10:00-12:00 booking on v_day + 7.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 7, v_day + 7, 600, 720,
            'approved', v_user, now())
        RETURNING id INTO v_first;

    -- AC2-H1 (12:00-14:00) and AC2-P1 (08:00-10:00, same old AM slot) approve.
    FOR v_bad IN SELECT * FROM (VALUES ('AC2-H1', 720, 840), ('AC2-P1', 480, 600)) AS t(label, s, e)
    LOOP
        INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
                start_date, end_date, start_minute, end_minute)
            VALUES (v_venue, v_user, gen_random_uuid(), v_day + 7, v_day + 7, v_bad.s, v_bad.e)
            RETURNING id INTO v_id;
        v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
        IF v_result->>'outcome' <> 'approved' THEN
            RAISE EXCEPTION '%: %', v_bad.label, v_result;
        END IF;
    END LOOP;

    -- AC2-B1: 11:45-14:00 overlaps the first booking by one step.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 7, v_day + 7, 705, 840)
        RETURNING id INTO v_id;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->>'outcome' <> 'refused'
       OR v_result->'refusal_codes' <> '["booking_conflict"]'::jsonb
       OR NOT (v_result->'conflicting_booking_ids' @> to_jsonb(ARRAY[v_first])) THEN
        RAISE EXCEPTION 'AC2-B1: %', v_result;
    END IF;
    IF (SELECT status FROM public.venue_booking_requests WHERE id = v_id) <> 'pending'
       OR (SELECT count(*) FROM public.venue_booking_refusals WHERE booking_request_id = v_id) <> 1 THEN
        RAISE EXCEPTION 'AC2-B1: refusal not recorded or status changed';
    END IF;

    -- AC2-P2: the next day approves; a range ending on that day conflicts.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 8, v_day + 8, 600, 720)
        RETURNING id INTO v_id;
    IF public.decide_venue_booking_request(v_id, 'approved', v_user)->>'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC2-P2: next day refused';
    END IF;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 5, v_day + 7, 1200, 1260)
        RETURNING id INTO v_id;
    IF public.decide_venue_booking_request(v_id, 'approved', v_user)->>'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC2-P2: 20:00-21:00 over three days refused';
    END IF;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 6, v_day + 7, 660, 780)
        RETURNING id INTO v_id;
    IF public.decide_venue_booking_request(v_id, 'approved', v_user)->>'outcome' <> 'refused' THEN
        RAISE EXCEPTION 'AC2-P2: spanning range approved';
    END IF;

    -- AC2-X1: a PM block refuses 11:00-13:00 by its touched slots, not 08:00-10:00.
    PERFORM public.create_venue_block(v_venue, v_day + 20, v_day + 20, 720, 1080,
        'maintenance', NULL, v_user);
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 20, v_day + 20, 660, 780)
        RETURNING id INTO v_id;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->'refusal_codes' <> '["active_block"]'::jsonb THEN
        RAISE EXCEPTION 'AC2-X1: %', v_result;
    END IF;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, gen_random_uuid(), v_day + 20, v_day + 20, 480, 600)
        RETURNING id INTO v_id;
    IF public.decide_venue_booking_request(v_id, 'approved', v_user)->>'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC2-X1: morning booking refused';
    END IF;

    RAISE NOTICE 'ALL SCRUM-65 BOOKING TIME VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
