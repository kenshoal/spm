-- Run after 0066_venue_holds.sql (SCRUM-18). Every change is rolled back.
-- Borrows the oldest auth user as the coordinator, organiser and Venue Staff.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_venue_holds.sql
--
-- Case IDs match docs/testcases/scrum_18_testcases.md. Times are on day D
-- (today + 20); the venue has 30 minutes setup and 45 turnaround. now() is
-- fixed for the whole transaction, so a hold expiring at now() tests the exact
-- expiry boundary.

BEGIN;

DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
    v_other uuid := gen_random_uuid();
    v_day date := current_date + 20;
    v_venue uuid;
    v_other_venue uuid;
    v_event uuid;
    v_closed_event uuid;
    v_review_event uuid;
    v_rival_event uuid;
    v_cancel_event uuid;
    v_moved_event uuid;
    v_result jsonb;
    v_hold uuid;
    v_second uuid;
    v_booking uuid;
    v_expired uuid;
    v_row public.venue_holds%ROWTYPE;
    v_count int;
    v_offset int;

    -- Places a hold for v_event by v_user, returning the function's result.
    v_place text := 'SELECT public.place_venue_hold($1, $2, $3, $3, $4, $5, $6, $7)';
BEGIN
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots, setup_minutes, turnaround_minutes)
        VALUES ('VERIFY SCRUM18 hold venue', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[], 30, 45)
        RETURNING id INTO v_venue;
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots, setup_minutes, turnaround_minutes)
        VALUES ('VERIFY SCRUM18 other venue', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[], 30, 45)
        RETURNING id INTO v_other_venue;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM18 event', 'Planning') RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM18 confirmed event', 'Confirmed') RETURNING id INTO v_closed_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM18 event under review', 'Under Review') RETURNING id INTO v_review_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM18 rival event', 'Planning') RETURNING id INTO v_rival_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM18 event to cancel', 'Planning') RETURNING id INTO v_cancel_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM18 event to reassign', 'Planning') RETURNING id INTO v_moved_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_user::text, v_user::text), (v_closed_event, v_user::text, v_user::text),
               (v_review_event, v_user::text, v_user::text), (v_rival_event, v_user::text, v_user::text),
               (v_cancel_event, v_user::text, v_user::text), (v_moved_event, v_user::text, v_user::text);

    -- AC1-H1: the assigned coordinator places a hold with an expiry.
    EXECUTE v_place INTO v_result
        USING v_venue, v_event, v_day, 600, 720, now() + interval '5 days', v_user;
    IF v_result->>'outcome' <> 'placed' THEN
        RAISE EXCEPTION 'AC1-H1: hold not placed: %', v_result;
    END IF;
    v_hold := (v_result->'hold'->>'id')::uuid;
    SELECT * INTO v_row FROM public.venue_holds WHERE id = v_hold;
    IF v_row.status <> 'active' OR v_row.placed_by <> v_user OR v_row.event_request_id <> v_event
       OR (v_row.start_minute, v_row.end_minute) <> (600, 720) THEN
        RAISE EXCEPTION 'AC1-H1: hold stored as %', to_jsonb(v_row);
    END IF;

    -- AC1-B1: an expiry exactly 7 days ahead is allowed; later, or not in the future, is refused.
    EXECUTE v_place INTO v_result
        USING v_venue, v_event, v_day + 3, 600, 720, now() + interval '7 days', v_user;
    IF v_result->>'outcome' <> 'placed' THEN
        RAISE EXCEPTION 'AC1-B1: 7-day expiry refused: %', v_result;
    END IF;
    BEGIN
        EXECUTE v_place USING v_venue, v_event, v_day + 4, 600, 720,
            now() + interval '7 days 1 second', v_user;
        RAISE EXCEPTION 'AC1-B1: expiry beyond 7 days accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    BEGIN
        EXECUTE v_place USING v_venue, v_event, v_day + 4, 600, 720, now(), v_user;
        RAISE EXCEPTION 'AC1-B1: expiry not in the future accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;

    -- AC1-N1: only the assigned coordinator, only before confirmation, only valid times.
    BEGIN
        EXECUTE v_place USING v_venue, v_event, v_day + 5, 600, 720, now() + interval '1 day', v_other;
        RAISE EXCEPTION 'AC1-N1: another user placed a hold';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;
    BEGIN
        EXECUTE v_place USING v_venue, v_closed_event, v_day + 5, 600, 720, now() + interval '1 day', v_user;
        RAISE EXCEPTION 'AC1-N1: a confirmed event placed a hold';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    BEGIN
        EXECUTE v_place USING v_venue, v_review_event, v_day + 5, 600, 720, now() + interval '1 day', v_user;
        RAISE EXCEPTION 'AC1-N1: an event still under review placed a hold';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    BEGIN
        EXECUTE v_place USING v_venue, v_event, v_day + 5, 610, 720, now() + interval '1 day', v_user;
        RAISE EXCEPTION 'AC1-N1: an off-step hold was accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;

    -- AC2-H1: an active hold refuses an overlapping hold, with padding (12:15 is in its turnaround).
    EXECUTE v_place INTO v_result
        USING v_venue, v_event, v_day, 735, 780, now() + interval '1 day', v_user;
    IF v_result->'refusal_codes' <> '["hold_conflict"]'::jsonb
       OR v_result->'conflicting_hold_ids' <> jsonb_build_array(v_hold) THEN
        RAISE EXCEPTION 'AC2-H1: overlapping hold not refused: %', v_result;
    END IF;

    -- AC2-B1: the exact gap of turnaround plus setup is free.
    EXECUTE v_place INTO v_result
        USING v_venue, v_event, v_day, 795, 840, now() + interval '25 hours', v_user;
    IF v_result->>'outcome' <> 'placed' THEN
        RAISE EXCEPTION 'AC2-B1: exact gap refused: %', v_result;
    END IF;
    v_second := (v_result->'hold'->>'id')::uuid;

    -- AC2-P1: another venue and another day are not affected.
    EXECUTE v_place INTO v_result
        USING v_other_venue, v_event, v_day, 600, 720, now() + interval '1 day', v_user;
    IF v_result->>'outcome' <> 'placed' THEN
        RAISE EXCEPTION 'AC2-P1: another venue refused: %', v_result;
    END IF;

    -- AC2-H2: an active hold refuses another event's overlapping booking approval, recorded
    -- with the hold.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, v_rival_event, v_day, v_day, 660, 720) RETURNING id INTO v_booking;
    v_result := public.decide_venue_booking_request(v_booking, 'approved', v_user);
    IF v_result->>'outcome' <> 'refused'
       OR v_result->'refusal_codes' <> '["hold_conflict"]'::jsonb
       OR v_result->'conflicting_hold_ids' <> jsonb_build_array(v_hold)
       OR (SELECT status FROM public.venue_booking_requests WHERE id = v_booking) <> 'pending'
       OR NOT EXISTS (SELECT 1 FROM public.venue_booking_refusals
                      WHERE booking_request_id = v_booking AND conflicting_hold_ids = ARRAY[v_hold]) THEN
        RAISE EXCEPTION 'AC2-H2: approval over a hold not refused: %', v_result;
    END IF;

    -- AC2-H3: the shared guard reports the hold to any caller, including a reschedule (0059),
    -- which refuses on any refusal code.
    v_result := private.check_booking_candidate(v_venue, v_day, v_day, 660, 720, ARRAY[gen_random_uuid()]);
    IF v_result->'refusal_codes' <> '["hold_conflict"]'::jsonb THEN
        RAISE EXCEPTION 'AC2-H3: guard ignored the hold: %', v_result;
    END IF;

    -- AC2-P2: an event's own hold, converted or not, never blocks that event's bookings: its
    -- approval passes, and a reschedule (0059 excludes the event's bookings) sees no hold.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute)
        VALUES (v_venue, v_user, v_event, v_day, v_day, 660, 720) RETURNING id INTO v_booking;
    IF private.check_booking_candidate(v_venue, v_day, v_day, 660, 720, ARRAY[v_booking])->'refusal_codes'
           <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC2-P2: an event''s own hold blocked its reschedule';
    END IF;
    UPDATE public.venue_booking_requests SET status = 'rejected', decision_reason = 'Verify',
        decided_by = v_user, decided_at = now()
    WHERE id = v_booking;

    -- AC2-H4: a hold over an approved booking is refused.
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_event, v_day + 1, v_day + 1, 600, 720, 'approved', v_user, now())
        RETURNING id INTO v_booking;
    EXECUTE v_place INTO v_result
        USING v_venue, v_event, v_day + 1, 735, 780, now() + interval '1 day', v_user;
    IF v_result->'refusal_codes' <> '["booking_conflict"]'::jsonb
       OR v_result->'conflicting_booking_ids' <> jsonb_build_array(v_booking) THEN
        RAISE EXCEPTION 'AC2-H4: hold over a booking not refused: %', v_result;
    END IF;

    -- AC3-B1: at its expiry time a hold stops protecting; just before, it still protects.
    INSERT INTO public.venue_holds (venue_id, event_request_id, start_date, end_date,
            start_minute, end_minute, expires_at, placed_by)
        VALUES (v_venue, v_event, v_day + 6, v_day + 6, 600, 720, now(), v_user);
    INSERT INTO public.venue_holds (venue_id, event_request_id, start_date, end_date,
            start_minute, end_minute, expires_at, placed_by)
        VALUES (v_venue, v_event, v_day + 7, v_day + 7, 600, 720, now() + interval '1 millisecond', v_user);
    IF private.check_booking_candidate(v_venue, v_day + 6, v_day + 6, 600, 720)->'refusal_codes'
           <> '[]'::jsonb
       OR private.check_booking_candidate(v_venue, v_day + 7, v_day + 7, 600, 720)->'refusal_codes'
           <> '["hold_conflict"]'::jsonb THEN
        RAISE EXCEPTION 'AC3-B1: the expiry boundary is wrong';
    END IF;

    -- AC3-N1: an expired hold cannot be released or converted.
    SELECT id INTO v_expired FROM public.venue_holds WHERE start_date = v_day + 6 AND venue_id = v_venue;
    BEGIN
        PERFORM public.release_venue_hold(v_expired, v_user);
        RAISE EXCEPTION 'AC3-N1: an expired hold was released';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    BEGIN
        PERFORM public.convert_venue_hold(v_expired,
            jsonb_build_object('id', gen_random_uuid(), 'requested_by', v_user),
            (SELECT updated_at FROM public.event_requests WHERE id = v_event));
        RAISE EXCEPTION 'AC3-N1: an expired hold was converted';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;

    -- AC4-H1: 24 hours before expiry an "expiring" notice is due, to the current coordinator;
    -- earlier it is not.
    SELECT count(*) INTO v_count
    FROM jsonb_array_elements(public.sweep_venue_holds(now())) AS n
    WHERE (n->>'hold_id')::uuid = v_second;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC4-H1: a notice was due more than 24 hours early';
    END IF;
    SELECT count(*) INTO v_count
    FROM jsonb_array_elements(public.sweep_venue_holds(now() + interval '2 hours')) AS n
    WHERE (n->>'hold_id')::uuid = v_second AND n->>'kind' = 'expiring'
      AND n->>'recipient_id' = v_user::text;
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'AC4-H1: expiring notice not due 23 hours before expiry';
    END IF;

    -- AC4-P1: a recorded notice is not listed again.
    PERFORM public.mark_venue_hold_notice(v_second, 'expiring');
    SELECT count(*) INTO v_count
    FROM jsonb_array_elements(public.sweep_venue_holds(now() + interval '3 hours')) AS n
    WHERE (n->>'hold_id')::uuid = v_second AND n->>'kind' = 'expiring';
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC4-P1: a recorded notice was listed again';
    END IF;

    -- AC3-H1 / AC4-H2: after expiry the sweep marks the hold expired and lists one "expired"
    -- notice, once.
    SELECT count(*) INTO v_count
    FROM jsonb_array_elements(public.sweep_venue_holds(now() + interval '2 days')) AS n
    WHERE (n->>'hold_id')::uuid = v_second AND n->>'kind' = 'expired';
    IF v_count <> 1 OR (SELECT status FROM public.venue_holds WHERE id = v_second) <> 'expired' THEN
        RAISE EXCEPTION 'AC3-H1: hold not expired with one notice';
    END IF;
    PERFORM public.mark_venue_hold_notice(v_second, 'expired');
    SELECT count(*) INTO v_count
    FROM jsonb_array_elements(public.sweep_venue_holds(now() + interval '3 days')) AS n
    WHERE (n->>'hold_id')::uuid = v_second;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC4-H2: the expired notice was listed again';
    END IF;

    -- AC5-N1: only the assigned coordinator can release.
    BEGIN
        PERFORM public.release_venue_hold(v_hold, v_other);
        RAISE EXCEPTION 'AC5-N1: another user released the hold';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;

    -- AC5-H1: converting creates a pending request that keeps the hold and does not conflict
    -- with it; approval makes it the booking and ends the hold.
    v_result := public.convert_venue_hold(v_hold,
        jsonb_build_object('id', gen_random_uuid(), 'requested_by', v_user),
        (SELECT updated_at FROM public.event_requests WHERE id = v_event));
    v_booking := (v_result->'booking'->>'id')::uuid;
    IF v_result->'booking'->>'status' <> 'pending'
       OR (v_result->'booking'->>'start_minute')::int <> 600
       OR (SELECT booking_request_id FROM public.venue_holds WHERE id = v_hold) <> v_booking
       OR (SELECT status FROM public.venue_holds WHERE id = v_hold) <> 'active' THEN
        RAISE EXCEPTION 'AC5-H1: conversion wrong: %', v_result;
    END IF;
    IF private.check_booking_candidate(v_venue, v_day, v_day, 735, 780)->'refusal_codes'
           <> '["hold_conflict"]'::jsonb THEN
        RAISE EXCEPTION 'AC5-H1: a pending conversion stopped protecting the time';
    END IF;
    BEGIN
        PERFORM public.convert_venue_hold(v_hold,
            jsonb_build_object('id', gen_random_uuid(), 'requested_by', v_user),
            (SELECT updated_at FROM public.event_requests WHERE id = v_event));
        RAISE EXCEPTION 'AC5-H1: a hold was converted twice';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    v_result := public.decide_venue_booking_request(v_booking, 'approved', v_user);
    IF v_result->>'outcome' <> 'approved'
       OR (SELECT status FROM public.venue_holds WHERE id = v_hold) <> 'converted' THEN
        RAISE EXCEPTION 'AC5-H1: approving the conversion did not end the hold: %', v_result;
    END IF;

    -- AC5-H2: a rejected conversion releases its hold.
    EXECUTE v_place INTO v_result
        USING v_venue, v_event, v_day + 2, 600, 720, now() + interval '1 day', v_user;
    v_hold := (v_result->'hold'->>'id')::uuid;
    v_result := public.convert_venue_hold(v_hold,
        jsonb_build_object('id', gen_random_uuid(), 'requested_by', v_user),
        (SELECT updated_at FROM public.event_requests WHERE id = v_event));
    PERFORM public.decide_venue_booking_request(
        (v_result->'booking'->>'id')::uuid, 'rejected', v_user, 'Room unavailable');
    IF (SELECT status FROM public.venue_holds WHERE id = v_hold) <> 'released' THEN
        RAISE EXCEPTION 'AC5-H2: a rejected conversion kept its hold';
    END IF;

    -- AC3-B3: a conversion decided after its hold expired, before the sweep ran, leaves the
    -- hold to the sweep: it ends as expired, with its notice, not converted or released.
    -- (Separate statements: a query sees rows as they were before a function it calls
    -- changed them.)
    FOR v_offset IN 11..12 LOOP
        EXECUTE v_place INTO v_result
            USING v_venue, v_event, v_day + v_offset, 600, 720, now() + interval '1 day', v_user;
        v_hold := (v_result->'hold'->>'id')::uuid;
        v_result := public.convert_venue_hold(v_hold,
            jsonb_build_object('id', gen_random_uuid(), 'requested_by', v_user),
            (SELECT updated_at FROM public.event_requests WHERE id = v_event));
        UPDATE public.venue_holds SET expires_at = now() - interval '1 minute' WHERE id = v_hold;
        PERFORM public.decide_venue_booking_request((v_result->'booking'->>'id')::uuid,
            CASE v_offset WHEN 11 THEN 'approved' ELSE 'rejected' END, v_user,
            CASE v_offset WHEN 12 THEN 'Room unavailable' END);
        IF (SELECT status FROM public.venue_holds WHERE id = v_hold) <> 'active' THEN
            RAISE EXCEPTION 'AC3-B3: a decision closed an expired hold (day +%)', v_offset;
        END IF;
        SELECT count(*) INTO v_count
        FROM jsonb_array_elements(public.sweep_venue_holds(now())) AS n
        WHERE (n->>'hold_id')::uuid = v_hold AND n->>'kind' = 'expired';
        IF v_count <> 1 OR (SELECT status FROM public.venue_holds WHERE id = v_hold) <> 'expired' THEN
            RAISE EXCEPTION 'AC3-B3: the sweep did not expire the hold with its notice (day +%)', v_offset;
        END IF;
    END LOOP;

    -- AC5-H3: releasing frees the time at once.
    EXECUTE v_place INTO v_result
        USING v_venue, v_event, v_day + 2, 600, 720, now() + interval '1 day', v_user;
    v_hold := (v_result->'hold'->>'id')::uuid;
    PERFORM public.release_venue_hold(v_hold, v_user);
    IF (SELECT status FROM public.venue_holds WHERE id = v_hold) <> 'released'
       OR private.check_booking_candidate(v_venue, v_day + 2, v_day + 2, 600, 720)->'refusal_codes'
           <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC5-H3: released hold still protects the time';
    END IF;

    -- AC3-P1: when its event is cancelled, a hold stops protecting at once and cannot be
    -- released or converted; no notice is sent for it.
    EXECUTE v_place INTO v_result
        USING v_venue, v_cancel_event, v_day + 9, 600, 720, now() + interval '2 hours', v_user;
    v_hold := (v_result->'hold'->>'id')::uuid;
    IF private.check_booking_candidate(v_venue, v_day + 9, v_day + 9, 600, 720)->'refusal_codes'
           <> '["hold_conflict"]'::jsonb THEN
        RAISE EXCEPTION 'AC3-P1: hold did not protect before cancellation';
    END IF;
    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_cancel_event;
    IF private.check_booking_candidate(v_venue, v_day + 9, v_day + 9, 600, 720)->'refusal_codes'
           <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC3-P1: a cancelled event''s hold still protects';
    END IF;
    BEGIN
        PERFORM public.release_venue_hold(v_hold, v_user);
        RAISE EXCEPTION 'AC3-P1: a cancelled event''s hold was released';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    SELECT count(*) INTO v_count
    FROM jsonb_array_elements(public.sweep_venue_holds(now() + interval '1 hour')) AS n
    WHERE (n->>'hold_id')::uuid = v_hold;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC3-P1: a notice was due for a cancelled event''s hold';
    END IF;

    -- AC5-P2: after a reassignment only the new coordinator can release or convert.
    EXECUTE v_place INTO v_result
        USING v_venue, v_moved_event, v_day + 10, 600, 720, now() + interval '1 day', v_user;
    v_hold := (v_result->'hold'->>'id')::uuid;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_moved_event, v_other::text, v_user::text);
    BEGIN
        PERFORM public.release_venue_hold(v_hold, v_user);
        RAISE EXCEPTION 'AC5-P2: the previous coordinator released the hold';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;
    IF (public.release_venue_hold(v_hold, v_other)).status <> 'released' THEN
        RAISE EXCEPTION 'AC5-P2: the new coordinator could not release the hold';
    END IF;

    -- DB-1: only the server can read holds or run the hold functions.
    IF has_table_privilege('anon', 'public.venue_holds', 'SELECT')
       OR has_table_privilege('authenticated', 'public.venue_holds', 'SELECT')
       OR has_table_privilege('service_role', 'public.venue_holds', 'INSERT')
       OR has_function_privilege('anon',
           'public.place_venue_hold(uuid, uuid, date, date, integer, integer, timestamptz, uuid)', 'EXECUTE')
       OR has_function_privilege('authenticated', 'public.release_venue_hold(uuid, uuid)', 'EXECUTE')
       OR has_function_privilege('authenticated', 'public.convert_venue_hold(uuid, jsonb, timestamptz)', 'EXECUTE')
       OR has_function_privilege('anon', 'public.sweep_venue_holds(timestamptz)', 'EXECUTE')
       OR NOT has_function_privilege('service_role',
           'public.place_venue_hold(uuid, uuid, date, date, integer, integer, timestamptz, uuid)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.mark_venue_hold_notice(uuid, text)', 'EXECUTE') THEN
        RAISE EXCEPTION 'DB-1: hold grants are wrong';
    END IF;

    RAISE NOTICE 'ALL SCRUM-18 VENUE HOLD VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
