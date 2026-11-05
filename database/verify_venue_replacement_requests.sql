-- Run after 0068_venue_replacement_requests.sql (SCRUM-63 AC4, AC5). Every change is
-- rolled back. Owned disposable scrum48_* database only. Borrows the oldest auth user.
-- Functions are called as service_role, as venueService calls them, so a missing
-- privilege fails here and not in production.
--   psql -X -v ON_ERROR_STOP=1 -d <dsn> -f database/verify_venue_replacement_requests.sql
--
-- Times are minutes after midnight (10:00 = 600). D is today + 10, Singapore.

BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '5s';

DO $$ BEGIN
    ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
END $$;

CREATE FUNCTION pg_temp.fail_clear() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('verify.fail_clear', true) = 'on' THEN
        RAISE EXCEPTION 'injected review clear failure' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER verify_replacement_fail_clear
    BEFORE UPDATE ON public.arrangement_reviews
    FOR EACH ROW EXECUTE FUNCTION pg_temp.fail_clear();

CREATE FUNCTION pg_temp.state() RETURNS jsonb LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object(
        'bookings', (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id), '[]') FROM public.venue_booking_requests x),
        'reviews', (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id), '[]') FROM public.arrangement_reviews x),
        'events', (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id), '[]') FROM public.event_requests x));
$$;

-- One booking request with the columns its status requires (0042's constraints).
CREATE FUNCTION pg_temp.add_booking(
    p_user uuid, p_venue uuid, p_event uuid, p_start date, p_end date,
    p_start_minute integer, p_end_minute integer, p_status text
) RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.venue_booking_requests (
        venue_id, requested_by, event_request_id, start_date, end_date,
        start_minute, end_minute, status, decided_by, decided_at, decision_reason)
    VALUES (
        p_venue, p_user, p_event, p_start, p_end, p_start_minute, p_end_minute,
        p_status::public.booking_request_status,
        CASE WHEN p_status IN ('approved', 'rejected') THEN p_user END,
        CASE WHEN p_status IN ('approved', 'rejected') THEN now() END,
        CASE WHEN p_status = 'rejected' THEN 'not suitable' END)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

DO $cases$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
    v_actor uuid := gen_random_uuid();      -- the event's coordinator
    v_other uuid := gen_random_uuid();      -- an unassigned coordinator
    v_day date := (now() AT TIME ZONE 'Asia/Singapore')::date + 10;
    v_e1 uuid; v_e2 uuid;
    v_v1 uuid; v_v2 uuid; v_v3 uuid;
    v_b1 uuid; v_b2 uuid; v_b3 uuid; v_b7 uuid; v_b8 uuid; v_other_booking uuid; v_blocker uuid;
    v_r1 uuid; v_r2 uuid; v_r3 uuid; v_r4 uuid; v_r5 uuid; v_r6 uuid;
    v_version timestamptz;
    v_row public.venue_booking_requests;
    v_result jsonb;
    v_before jsonb;
    v_b1_before jsonb;
    v_event_before jsonb;
    v_flag public.arrangement_reviews;
    v_count int;
    v_cancelled int;
BEGIN
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance, venue_requirements)
        VALUES (v_user, 'VERIFY SCRUM63 replacement event', 'Planning', 40, 'Stage and mics') RETURNING id INTO v_e1;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM63 other event', 'Planning') RETURNING id INTO v_e2;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_e1, v_actor::text, 'verify63');
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM63 blocked hall', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
        RETURNING id INTO v_v1;
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM63 second hall', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
        RETURNING id INTO v_v2;
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM63 third hall', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
        RETURNING id INTO v_v3;

    -- B1 09:00-12:00 on D at venue 1, approved; blocking venue 1 10:00-11:00 flags it (0064).
    v_b1 := pg_temp.add_booking(v_user, v_v1, v_e1, v_day, v_day, 540, 720, 'approved');
    SET LOCAL ROLE service_role;
    PERFORM public.create_venue_block(v_v1, v_day, v_day, 600, 660, 'maintenance', 'VERIFY SCRUM63', v_user);
    RESET ROLE;
    SELECT * INTO v_flag FROM public.arrangement_reviews
        WHERE arrangement_id = v_b1 AND trigger_type = 'venue_block' AND cleared_at IS NULL;
    ASSERT v_flag.id IS NOT NULL, 'SETUP: B1 was not flagged by the block';
    SELECT updated_at INTO v_version FROM public.event_requests WHERE id = v_e1;

    -- AC4-N1: a booking with no open flag cannot be replaced.
    v_b2 := pg_temp.add_booking(v_user, v_v1, v_e1, v_day + 20, v_day + 20, 540, 720, 'approved');
    v_before := pg_temp.state();
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(v_b2, gen_random_uuid(), v_v2, v_actor, v_version);
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N1: an unflagged booking was replaced';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        RESET ROLE;
        IF SQLERRM NOT LIKE '%not flagged%' THEN RAISE; END IF;
    END;
    ASSERT pg_temp.state() = v_before, 'AC4-N1: a refused request changed state';

    -- AC4-N2: a booking that is not approved cannot be replaced, even with a flag.
    v_b3 := pg_temp.add_booking(v_user, v_v1, v_e1, v_day + 21, v_day + 21, 540, 720, 'pending');
    INSERT INTO public.arrangement_reviews (event_request_id, arrangement, arrangement_id, trigger_id,
            trigger_type, changed_fields, reason)
        VALUES (v_e1, 'venue_booking', v_b3, gen_random_uuid(), 'venue_block', '{}', 'VERIFY forced flag');
    v_before := pg_temp.state();
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(v_b3, gen_random_uuid(), v_v2, v_actor, v_version);
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N2: a pending booking was replaced';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        RESET ROLE;
        IF SQLERRM NOT LIKE '%not approved%' THEN RAISE; END IF;
    END;
    ASSERT pg_temp.state() = v_before, 'AC4-N2: a refused request changed state';

    -- AC4-N3: the blocked venue is refused as the replacement.
    v_before := pg_temp.state();
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(v_b1, gen_random_uuid(), v_v1, v_actor, v_version);
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N3: the same venue was accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN
        RESET ROLE;
        IF SQLERRM NOT LIKE '%different venue%' THEN RAISE; END IF;
    END;
    ASSERT pg_temp.state() = v_before, 'AC4-N3: a refused request changed state';

    -- AC4-N4: an unknown venue is refused.
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(v_b1, gen_random_uuid(), gen_random_uuid(), v_actor, v_version);
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N4: an unknown venue was accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN RESET ROLE;
    END;
    ASSERT pg_temp.state() = v_before, 'AC4-N4: a refused request changed state';

    -- AC4-N6: the event changed since the page loaded.
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(v_b1, gen_random_uuid(), v_v2, v_actor, v_version - interval '1 second');
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N6: a stale event version was accepted';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        RESET ROLE;
        IF SQLERRM NOT LIKE '%changed%' THEN RAISE; END IF;
    END;
    ASSERT pg_temp.state() = v_before, 'AC4-N6: a refused request changed state';

    -- AC4-N7 / AC4-N8: a coordinator who is not the event's current coordinator is refused.
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(v_b1, gen_random_uuid(), v_v2, v_other, v_version);
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N7: an unassigned coordinator was accepted';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN RESET ROLE;
    END;
    ASSERT pg_temp.state() = v_before, 'AC4-N7: a refused request changed state';

    -- AC4-N9: an unknown booking.
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(gen_random_uuid(), gen_random_uuid(), v_v2, v_actor, v_version);
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N9: an unknown booking was accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN RESET ROLE;
    END;

    -- AC4-H1: the assigned coordinator requests a replacement at venue 2.
    SELECT to_jsonb(b) INTO v_b1_before FROM public.venue_booking_requests b WHERE id = v_b1;
    SELECT to_jsonb(e) INTO v_event_before FROM public.event_requests e WHERE id = v_e1;
    v_r1 := gen_random_uuid();
    SET LOCAL ROLE service_role;
    v_row := public.create_replacement_venue_booking_request(v_b1, v_r1, v_v2, v_actor, v_version);
    RESET ROLE;
    IF v_row.id <> v_r1 OR v_row.status <> 'pending' OR v_row.venue_id <> v_v2
       OR v_row.event_request_id <> v_e1 OR v_row.requested_by <> v_actor
       OR (v_row.start_date, v_row.end_date, v_row.start_minute, v_row.end_minute) <> (v_day, v_day, 540, 720)
       OR v_row.replaces_booking_id <> v_b1
       OR v_row.event_name <> 'VERIFY SCRUM63 replacement event' OR v_row.expected_attendance <> 40
       OR v_row.requirements_note <> 'Stage and mics'
       OR v_row.decided_by IS NOT NULL OR v_row.cancelled_by IS NOT NULL THEN
        RAISE EXCEPTION 'AC4-H1: wrong replacement stored: %', to_jsonb(v_row);
    END IF;
    IF (SELECT to_jsonb(b) FROM public.venue_booking_requests b WHERE id = v_b1) IS DISTINCT FROM v_b1_before
       OR (SELECT to_jsonb(e) FROM public.event_requests e WHERE id = v_e1) IS DISTINCT FROM v_event_before
       OR NOT EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE id = v_flag.id AND cleared_at IS NULL) THEN
        RAISE EXCEPTION 'AC4-H1: the original booking, its flag or the event changed';
    END IF;

    -- AC4-N5: a second replacement while one is pending is refused.
    v_before := pg_temp.state();
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.create_replacement_venue_booking_request(v_b1, gen_random_uuid(), v_v3, v_actor, v_version);
        RESET ROLE;
        RAISE EXCEPTION 'AC4-N5: a second active replacement was accepted';
    EXCEPTION WHEN unique_violation THEN RESET ROLE;
    END;
    ASSERT pg_temp.state() = v_before, 'AC4-N5: a refused request changed state';

    -- AC5-N1: rejecting the replacement leaves the old booking and flag, and frees the link.
    SET LOCAL ROLE service_role;
    v_result := public.decide_venue_booking_request(v_r1, 'rejected', v_user, 'not suitable', NULL);
    RESET ROLE;
    IF v_result ->> 'outcome' <> 'rejected'
       OR (SELECT status FROM public.venue_booking_requests WHERE id = v_b1) <> 'approved'
       OR NOT EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE id = v_flag.id AND cleared_at IS NULL) THEN
        RAISE EXCEPTION 'AC5-N1: a rejected replacement changed the old booking or its flag: %', v_result;
    END IF;
    v_r2 := gen_random_uuid();
    SET LOCAL ROLE service_role;
    PERFORM public.create_replacement_venue_booking_request(v_b1, v_r2, v_v3, v_actor, v_version);
    RESET ROLE;

    -- AC5-N3: the coordinator cancelling the replacement leaves the old booking and flag.
    SET LOCAL ROLE service_role;
    PERFORM public.cancel_venue_booking_request(v_r2, v_actor);
    RESET ROLE;
    IF (SELECT status FROM public.venue_booking_requests WHERE id = v_b1) <> 'approved'
       OR NOT EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE id = v_flag.id AND cleared_at IS NULL) THEN
        RAISE EXCEPTION 'AC5-N3: a cancelled replacement changed the old booking or its flag';
    END IF;

    -- AC5-N2: a replacement that now clashes is refused and changes nothing. Another event
    -- holds venue 2 at 09:00-12:00 on D.
    v_blocker := pg_temp.add_booking(v_user, v_v2, v_e2, v_day, v_day, 540, 720, 'approved');
    v_r3 := gen_random_uuid();
    SET LOCAL ROLE service_role;
    PERFORM public.create_replacement_venue_booking_request(v_b1, v_r3, v_v2, v_actor, v_version);
    RESET ROLE;
    v_before := pg_temp.state();
    SET LOCAL ROLE service_role;
    v_result := public.decide_venue_booking_request(v_r3, 'approved', v_user, NULL, NULL);
    RESET ROLE;
    IF v_result ->> 'outcome' <> 'refused' THEN
        RAISE EXCEPTION 'AC5-N2: a clashing replacement was not refused: %', v_result;
    END IF;
    IF (SELECT status FROM public.venue_booking_requests WHERE id = v_b1) <> 'approved'
       OR NOT EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE id = v_flag.id AND cleared_at IS NULL)
       OR (SELECT status FROM public.venue_booking_requests WHERE id = v_r3) <> 'pending' THEN
        RAISE EXCEPTION 'AC5-N2: a refused replacement changed the old booking, its flag or itself';
    END IF;
    SET LOCAL ROLE service_role;
    PERFORM public.decide_venue_booking_request(v_r3, 'rejected', v_user, 'clashes', NULL);
    RESET ROLE;

    -- AC5-N4: if clearing the flag fails, the approval is undone too.
    v_b8 := pg_temp.add_booking(v_user, v_v1, v_e1, v_day + 40, v_day + 40, 540, 720, 'approved');
    SET LOCAL ROLE service_role;
    PERFORM public.create_venue_block(v_v1, v_day + 40, v_day + 40, 600, 660, 'maintenance', 'VERIFY N4', v_user);
    RESET ROLE;
    v_r6 := gen_random_uuid();
    SET LOCAL ROLE service_role;
    PERFORM public.create_replacement_venue_booking_request(v_b8, v_r6, v_v2, v_actor, v_version);
    RESET ROLE;
    v_before := pg_temp.state();
    PERFORM set_config('verify.fail_clear', 'on', true);
    BEGIN
        SET LOCAL ROLE service_role;
        PERFORM public.decide_venue_booking_request(v_r6, 'approved', v_user, NULL, NULL);
        RESET ROLE;
        RAISE EXCEPTION 'AC5-N4: the approval succeeded despite the failure';
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        RESET ROLE;
        IF SQLERRM <> 'injected review clear failure' THEN RAISE; END IF;
    END;
    PERFORM set_config('verify.fail_clear', 'off', true);
    ASSERT pg_temp.state() = v_before, 'AC5-N4: a failed approval left changes behind';

    -- AC5-H1: approving the replacement cancels the old booking and clears its flag together.
    v_r4 := gen_random_uuid();
    SET LOCAL ROLE service_role;
    PERFORM public.create_replacement_venue_booking_request(v_b1, v_r4, v_v3, v_actor, v_version);
    RESET ROLE;
    SELECT count(*) INTO v_cancelled FROM public.venue_booking_requests WHERE status = 'cancelled';
    SET LOCAL ROLE service_role;
    v_result := public.decide_venue_booking_request(v_r4, 'approved', v_user, NULL, NULL);
    RESET ROLE;
    IF v_result ->> 'outcome' <> 'approved'
       OR (SELECT status FROM public.venue_booking_requests WHERE id = v_r4) <> 'approved' THEN
        RAISE EXCEPTION 'AC5-H1: the replacement was not approved: %', v_result;
    END IF;
    SELECT * INTO v_row FROM public.venue_booking_requests WHERE id = v_b1;
    IF v_row.status <> 'cancelled' OR v_row.cancelled_by IS DISTINCT FROM v_user OR v_row.cancelled_at IS NULL
       OR v_row.decided_by IS NULL OR v_row.decided_at IS NULL
       OR (v_row.venue_id, v_row.start_date, v_row.start_minute, v_row.end_minute) <> (v_v1, v_day, 540, 720) THEN
        RAISE EXCEPTION 'AC5-H1: the old booking was not cancelled as expected: %', to_jsonb(v_row);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.arrangement_reviews
                   WHERE id = v_flag.id AND cleared_at IS NOT NULL AND cleared_by = v_user) THEN
        RAISE EXCEPTION 'AC5-H1: the flag was not cleared';
    END IF;
    IF (SELECT count(*) FROM public.venue_booking_requests WHERE status = 'cancelled') <> v_cancelled + 1 THEN
        RAISE EXCEPTION 'AC5-H1: more than one booking was cancelled';
    END IF;

    -- AC5-N5: if the old booking was already cancelled by the coordinator, the replacement
    -- is still approved and the flag is cleared; nothing errors.
    v_b7 := pg_temp.add_booking(v_user, v_v1, v_e1, v_day + 30, v_day + 30, 540, 720, 'approved');
    SET LOCAL ROLE service_role;
    PERFORM public.create_venue_block(v_v1, v_day + 30, v_day + 30, 600, 660, 'maintenance', 'VERIFY N5', v_user);
    RESET ROLE;
    v_r5 := gen_random_uuid();
    SET LOCAL ROLE service_role;
    PERFORM public.create_replacement_venue_booking_request(v_b7, v_r5, v_v2, v_actor, v_version);
    PERFORM public.cancel_venue_booking_request(v_b7, v_actor);
    v_result := public.decide_venue_booking_request(v_r5, 'approved', v_user, NULL, NULL);
    RESET ROLE;
    IF v_result ->> 'outcome' <> 'approved'
       OR (SELECT status FROM public.venue_booking_requests WHERE id = v_b7) <> 'cancelled'
       OR (SELECT cancelled_by FROM public.venue_booking_requests WHERE id = v_b7) <> v_actor
       OR EXISTS (SELECT 1 FROM public.arrangement_reviews
                  WHERE arrangement_id = v_b7 AND trigger_type = 'venue_block' AND cleared_at IS NULL) THEN
        RAISE EXCEPTION 'AC5-N5: an already cancelled original broke the approval: %', v_result;
    END IF;

    -- AC5-X2: an ordinary approval, with no link, cancels nothing.
    v_b1 := pg_temp.add_booking(v_user, v_v3, v_e2, v_day + 50, v_day + 50, 540, 600, 'pending');
    SELECT count(*) INTO v_cancelled FROM public.venue_booking_requests WHERE status = 'cancelled';
    SET LOCAL ROLE service_role;
    v_result := public.decide_venue_booking_request(v_b1, 'approved', v_user, NULL, NULL);
    RESET ROLE;
    IF v_result ->> 'outcome' <> 'approved'
       OR (SELECT count(*) FROM public.venue_booking_requests WHERE status = 'cancelled') <> v_cancelled THEN
        RAISE EXCEPTION 'AC5-X2: an ordinary approval changed other bookings: %', v_result;
    END IF;

    -- DB-1: only the server can call the new function; direct inserts stay revoked; the link
    -- is unique while a replacement is active.
    IF has_function_privilege('anon', 'public.create_replacement_venue_booking_request(uuid, uuid, uuid, uuid, timestamptz)', 'EXECUTE')
       OR has_function_privilege('authenticated', 'public.create_replacement_venue_booking_request(uuid, uuid, uuid, uuid, timestamptz)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.create_replacement_venue_booking_request(uuid, uuid, uuid, uuid, timestamptz)', 'EXECUTE')
       OR has_table_privilege('service_role', 'public.venue_booking_requests', 'INSERT')
       OR NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'venue_booking_replacement_active_idx') THEN
        RAISE EXCEPTION 'DB-1: privileges or the active-replacement index are wrong';
    END IF;

    RAISE NOTICE 'ALL SCRUM-63 VENUE REPLACEMENT VERIFICATIONS PASSED';
END;
$cases$;

ROLLBACK;
