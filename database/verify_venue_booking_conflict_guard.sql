-- Run after 0054_venue_booking_conflict_guard.sql (SCRUM-20). Every change is
-- rolled back. Uses no DELETE or UPDATE. Borrows the oldest auth user, which
-- requested_by and decided_by need.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_venue_booking_conflict_guard.sql
--
-- Times on the test day; "30 / 45" means setup 30 minutes, turnaround 45.

BEGIN;

DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
    v_day date := current_date + 40;
    v_venue uuid;
    v_a uuid;
    v_c uuid;
    v_id uuid;
    v_result jsonb;
    v_count int;

    -- Inserts a pending request at the venue.
    v_sql text := 'INSERT INTO public.venue_booking_requests (venue_id, requested_by, '
        'event_request_id, start_date, end_date, start_minute, end_minute) '
        'VALUES ($1, $2, gen_random_uuid(), $3, $4, $5, $6) RETURNING id';
BEGIN
    -- Venue 30 / 45 with approved A 10:00-12:00 and C 17:00-18:00.
    INSERT INTO public.venues (name, location, max_capacity, facilities,
            accessibility_features, supported_layouts, operating_slots, setup_minutes, turnaround_minutes)
        VALUES ('VERIFY SCRUM20 guard venue', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM', 'PM', 'NIGHT']::public.booking_slot[], 30, 45)
        RETURNING id INTO v_venue;
    EXECUTE v_sql INTO v_a USING v_venue, v_user, v_day, v_day, 600, 720;
    EXECUTE v_sql INTO v_c USING v_venue, v_user, v_day, v_day, 1020, 1080;
    IF public.decide_venue_booking_request(v_a, 'approved', v_user)->>'outcome' <> 'approved'
       OR public.decide_venue_booking_request(v_c, 'approved', v_user)->>'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'setup: fixture bookings were not approved';
    END IF;

    -- AC3-H2: padding creates a conflict the booked times alone would not.
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 735, 780);
    IF v_result <> jsonb_build_object('refusal_codes', '["booking_conflict"]'::jsonb,
                                      'conflicting_booking_ids', jsonb_build_array(v_a)) THEN
        RAISE EXCEPTION 'AC3-H2: 12:15-13:00 not refused: %', v_result;
    END IF;

    -- AC5-B1: after A, a gap equal to turnaround plus setup is allowed; one step less is not.
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 795, 840);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC5-B1: 75-minute gap refused: %', v_result;
    END IF;
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 780, 840);
    IF v_result->'conflicting_booking_ids' <> jsonb_build_array(v_a) THEN
        RAISE EXCEPTION 'AC5-B1: 60-minute gap allowed: %', v_result;
    END IF;

    -- AC5-B2: the same boundary before A (08:00-08:45 allowed, 08:00-09:00 not).
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 480, 525);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC5-B2: 75-minute gap before A refused: %', v_result;
    END IF;
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 480, 540);
    IF v_result->'conflicting_booking_ids' <> jsonb_build_array(v_a) THEN
        RAISE EXCEPTION 'AC5-B2: 60-minute gap before A allowed: %', v_result;
    END IF;

    -- AC1-H3: every clashing booking is reported, in start order.
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 690, 1020);
    IF v_result->'conflicting_booking_ids' <> jsonb_build_array(v_a, v_c) THEN
        RAISE EXCEPTION 'AC1-H3: expected A then C: %', v_result;
    END IF;

    -- AC1-P3 / AC1-P4: date ranges clash only when they share a day.
    v_result := private.check_booking_candidate(v_venue, v_day - 1, v_day, 600, 720);
    IF v_result->'conflicting_booking_ids' <> jsonb_build_array(v_a) THEN
        RAISE EXCEPTION 'AC1-P3: overlapping date range allowed: %', v_result;
    END IF;
    v_result := private.check_booking_candidate(v_venue, v_day + 1, v_day + 2, 600, 720);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC1-P4: separate dates refused: %', v_result;
    END IF;

    -- AC1-P1: pending, rejected and cancelled requests never conflict.
    EXECUTE v_sql INTO v_id USING v_venue, v_user, v_day + 3, v_day + 3, 600, 720;
    EXECUTE v_sql INTO v_id USING v_venue, v_user, v_day + 3, v_day + 3, 600, 720;
    PERFORM public.decide_venue_booking_request(v_id, 'rejected', v_user, 'Verify');
    EXECUTE v_sql INTO v_id USING v_venue, v_user, v_day + 3, v_day + 3, 600, 720;
    PERFORM public.cancel_venue_booking_request(v_id, v_user);
    v_result := private.check_booking_candidate(v_venue, v_day + 3, v_day + 3, 600, 720);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC1-P1: a non-approved request conflicts: %', v_result;
    END IF;

    -- AC4-P1: a booking never conflicts with itself.
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 600, 780, ARRAY[v_a]);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC4-P1: A conflicts with itself: %', v_result;
    END IF;

    -- AC4-H1: moving C onto A's time is refused with A; AC4-H2: a free time is clear.
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 660, 720, ARRAY[v_c]);
    IF v_result <> jsonb_build_object('refusal_codes', '["booking_conflict"]'::jsonb,
                                      'conflicting_booking_ids', jsonb_build_array(v_a)) THEN
        RAISE EXCEPTION 'AC4-H1: reschedule onto A not refused: %', v_result;
    END IF;
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 1080, 1140, ARRAY[v_c]);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC4-H2: reschedule to a free time refused: %', v_result;
    END IF;

    -- AC3-B1 / AC3-B2: setup and turnaround must stay inside 07:00-24:00.
    v_result := private.check_booking_candidate(v_venue, v_day + 5, v_day + 5, 450, 540);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC3-B1: 07:30 start with 30 setup refused: %', v_result;
    END IF;
    v_result := private.check_booking_candidate(v_venue, v_day + 5, v_day + 5, 435, 540);
    IF v_result->'refusal_codes' <> '["setup_outside_window"]'::jsonb THEN
        RAISE EXCEPTION 'AC3-B1: 07:15 start with 30 setup allowed: %', v_result;
    END IF;
    v_result := private.check_booking_candidate(v_venue, v_day + 5, v_day + 5, 1320, 1395);
    IF v_result->'refusal_codes' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC3-B2: 23:15 end with 45 turnaround refused: %', v_result;
    END IF;
    v_result := private.check_booking_candidate(v_venue, v_day + 5, v_day + 5, 1320, 1410);
    IF v_result->'refusal_codes' <> '["turnaround_outside_window"]'::jsonb THEN
        RAISE EXCEPTION 'AC3-B2: 23:30 end with 45 turnaround allowed: %', v_result;
    END IF;

    -- G-N1: bad input is an error, not a refusal.
    BEGIN
        PERFORM private.check_booking_candidate(gen_random_uuid(), v_day, v_day, 600, 720);
        RAISE EXCEPTION 'G-N1: unknown venue accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;
    BEGIN
        PERFORM private.check_booking_candidate(v_venue, v_day, v_day, 610, 720);
        RAISE EXCEPTION 'G-N1: off-step time accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    BEGIN
        PERFORM private.check_booking_candidate(v_venue, v_day, v_day - 1, 600, 720);
        RAISE EXCEPTION 'G-N1: reversed dates accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    BEGIN
        PERFORM private.check_booking_candidate(v_venue, v_day, v_day, NULL, 720);
        RAISE EXCEPTION 'G-N1: missing time accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;

    -- AC1 / AC3 in approval: a padded overlap is refused, recorded and left pending.
    EXECUTE v_sql INTO v_id USING v_venue, v_user, v_day, v_day, 735, 780;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->>'outcome' <> 'refused'
       OR v_result->'refusal_codes' <> '["booking_conflict"]'::jsonb
       OR v_result->'conflicting_booking_ids' <> jsonb_build_array(v_a)
       OR v_result->'booking'->>'status' <> 'pending' THEN
        RAISE EXCEPTION 'AC1: padded overlap approved: %', v_result;
    END IF;
    SELECT count(*) INTO v_count FROM public.venue_booking_refusals AS f
    WHERE f.booking_request_id = v_id
      AND f.refusal_codes = '{booking_conflict}' AND f.conflicting_booking_ids = ARRAY[v_a];
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'AC1: refusal not recorded (% rows)', v_count;
    END IF;

    -- AC3 in approval: padding outside the window is refused and recorded.
    EXECUTE v_sql INTO v_id USING v_venue, v_user, v_day + 6, v_day + 6, 435, 540;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->'refusal_codes' <> '["setup_outside_window"]'::jsonb THEN
        RAISE EXCEPTION 'AC3: setup outside the window approved: %', v_result;
    END IF;
    SELECT count(*) INTO v_count FROM public.venue_booking_refusals AS f
    WHERE f.booking_request_id = v_id AND f.refusal_codes = '{setup_outside_window}';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'AC3: window refusal not recorded (% rows)', v_count;
    END IF;

    -- AC5 in approval: the exact gap is approved.
    EXECUTE v_sql INTO v_id USING v_venue, v_user, v_day, v_day, 795, 840;
    v_result := public.decide_venue_booking_request(v_id, 'approved', v_user);
    IF v_result->>'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC5: exact gap refused in approval: %', v_result;
    END IF;

    -- DB-1: only the server can run the guard.
    IF has_function_privilege('anon',
           'private.check_booking_candidate(uuid, date, date, integer, integer, uuid[])', 'EXECUTE')
       OR has_function_privilege('authenticated',
           'private.check_booking_candidate(uuid, date, date, integer, integer, uuid[])', 'EXECUTE')
       OR NOT has_function_privilege('service_role',
           'private.check_booking_candidate(uuid, date, date, integer, integer, uuid[])', 'EXECUTE') THEN
        RAISE EXCEPTION 'DB-1: check_booking_candidate grants are wrong';
    END IF;

    RAISE NOTICE 'ALL SCRUM-20 CONFLICT GUARD VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
