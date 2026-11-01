-- Run after 0069 to 0078 (Release 1 hotfixes 3, 4, 8 to 13, 16, 19). Every change is
-- rolled back. Borrows the oldest auth user as organiser, coordinator and staff.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_release_1_hotfixes.sql
--
-- Needs one row in staff_roles for the borrowed user as safety_officer: it is added
-- here and rolled back with everything else.

BEGIN;

DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_who text := v_user::text;
    v_today date := (now() AT TIME ZONE 'Asia/Singapore')::date;
    v_day date := (now() AT TIME ZONE 'Asia/Singapore')::date + 10;
    v_event uuid; v_other uuid; v_venue uuid; v_venue2 uuid;
    v_booking uuid; v_req uuid; v_equip uuid; v_res uuid; v_res2 uuid;
    v_row public.event_requests;
    v_count integer;
    v_text text;
    v_ts timestamptz;
BEGIN
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_user, 'safety_officer')
        ON CONFLICT DO NOTHING;

    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance)
        VALUES (v_user, 'VERIFY HOTFIX event', 'Planning', 50) RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_who, v_who);
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY HOTFIX venue', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_venue;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
            end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_event, v_day, v_day, 600, 720, 'approved', v_user, now())
        RETURNING id INTO v_booking;

    -- 0069 AC3-H1 (happy): a rejection returns the event to Planning, flags the target
    UPDATE public.event_requests SET status = 'Safety Review' WHERE id = v_event;
    v_row := public.decide_safety_review(v_event, v_user, 'rejected', 'Exits blocked',
        jsonb_build_array(jsonb_build_object('arrangement', 'venue_booking', 'id', v_booking)));
    ASSERT v_row.status = 'Planning', 'AC3-H1: a rejection must return the event to Planning';
    ASSERT (SELECT decision FROM public.safety_reviews WHERE event_request_id = v_event) = 'rejected',
        'AC3-H1: the rejection is kept distinct from asking for changes';
    ASSERT (SELECT count(*) FROM public.arrangement_reviews
            WHERE event_request_id = v_event AND arrangement_id = v_booking
              AND trigger_type = 'safety_recheck') = 1,
        'AC3-H1: the chosen arrangement is flagged';
    -- AC3-N1 (negative): a rejection needs a reason and leaves everything unchanged
    UPDATE public.event_requests SET status = 'Safety Review' WHERE id = v_event;
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_user, 'rejected', '  ', '[]'::jsonb);
        RAISE EXCEPTION 'AC3-N1: reasonless rejection accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    ASSERT (SELECT status FROM public.event_requests WHERE id = v_event) = 'Safety Review',
        'AC3-N1: a refused rejection changed the status';
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_event;

    -- 0070 AC4-H1 (happy): the assigned coordinator sets the registration settings
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;
    v_row := public.set_event_registration_settings(v_event, v_who, now() - interval '1 day',
        now() + interval '5 days', 2, now());
    ASSERT v_row.registration_capacity = 2 AND v_row.registration_closes_at > v_row.registration_opens_at,
        'AC4-H1: settings not saved';
    -- AC4-N1 (negative): another coordinator is refused
    BEGIN
        PERFORM public.set_event_registration_settings(v_event, 'someone-else', now(),
            now() + interval '1 day', 2, now());
        RAISE EXCEPTION 'AC4-N1: unassigned caller accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    -- AC4-B1, AC4-B2 (boundary): closing at the opening instant, and capacity 0, are refused
    FOR v_count IN 0..1 LOOP
        BEGIN
            PERFORM public.set_event_registration_settings(v_event, v_who, now(),
                CASE v_count WHEN 0 THEN now() ELSE now() + interval '1 day' END,
                CASE v_count WHEN 0 THEN 5 ELSE 0 END, now());
            RAISE EXCEPTION 'AC4-B: invalid settings accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    END LOOP;
    -- AC4-B3 (boundary): capacity equal to the places taken is accepted, one below is refused
    INSERT INTO public.event_registrations (event_request_id, attendee_id) VALUES (v_event, v_user);
    INSERT INTO public.event_registrations (event_request_id, attendee_id)
        SELECT v_event, id FROM auth.users ORDER BY created_at, id OFFSET 1 LIMIT 1;
    PERFORM public.set_event_registration_settings(v_event, v_who, now() - interval '1 day',
        now() + interval '5 days', 2, now());
    BEGIN
        PERFORM public.set_event_registration_settings(v_event, v_who, now() - interval '1 day',
            now() + interval '5 days', 1, now());
        RAISE EXCEPTION 'AC4-B3: capacity below the places taken accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    ASSERT (SELECT registration_capacity FROM public.event_requests WHERE id = v_event) = 2,
        'AC4-B3: a refused capacity changed the event';
    DELETE FROM public.event_registrations WHERE event_request_id = v_event;

    -- 0073 AC10-H1 (happy): cancelling releases bookings and reservations, with the audit
    INSERT INTO public.equipment (type, total_owned_quantity, home_location, operational_status)
        VALUES ('VERIFY projector', 5, 'Test wing', 'AVAILABLE') RETURNING id INTO v_equip;
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
        VALUES (v_event, 'VERIFY projector', 2, v_user) RETURNING id INTO v_req;
    INSERT INTO public.equipment_reservations (equipment_id, event_request_id, requirement_id,
            quantity, collection_date, return_date, created_by)
        VALUES (v_equip, v_event, v_req, 2, v_day - 1, v_day, v_user) RETURNING id INTO v_res;
    INSERT INTO public.equipment_reservations (equipment_id, event_request_id, requirement_id,
            quantity, collection_date, return_date, created_by)
        VALUES (v_equip, v_event, v_req, 1, v_day - 1, v_day, v_user) RETURNING id INTO v_res2;

    -- 0072 AC11-H1 (happy): a release moves the row to the audit table and frees the units
    PERFORM public.release_equipment_reservation(v_res2, v_user, 'Broken');
    ASSERT NOT EXISTS (SELECT 1 FROM public.equipment_reservations WHERE id = v_res2),
        'AC11-H1: a released reservation is still counted';
    ASSERT (SELECT reason FROM public.equipment_reservation_releases WHERE reservation_id = v_res2) = 'Broken',
        'AC11-H1: the release is not recorded';
    -- AC11-N1, AC11-N2 (negative): a missing reservation and a blank reason are refused
    BEGIN
        PERFORM public.release_equipment_reservation(v_res2, v_user, 'again');
        RAISE EXCEPTION 'AC11-N1: released twice' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
    BEGIN
        PERFORM public.release_equipment_reservation(v_res, v_user, '  ');
        RAISE EXCEPTION 'AC11-N2: blank reason accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    ASSERT EXISTS (SELECT 1 FROM public.equipment_reservations WHERE id = v_res),
        'AC11-N2: a refused release removed the reservation';

    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_event;
    ASSERT (SELECT status FROM public.venue_booking_requests WHERE id = v_booking) = 'cancelled',
        'AC10-H1: the booking stays live after cancellation';
    ASSERT NOT EXISTS (SELECT 1 FROM public.equipment_reservations WHERE event_request_id = v_event),
        'AC10-H1: reservations stay after cancellation';
    ASSERT (SELECT count(*) FROM public.equipment_reservation_releases
            WHERE event_request_id = v_event AND reason = 'Event cancelled') = 1,
        'AC10-H1: the cancellation release is not recorded';
    -- AC10-N1 (negative): another event's bookings are untouched by a cancellation
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY HOTFIX other', 'Planning') RETURNING id INTO v_other;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
            end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_other, v_day + 1, v_day + 1, 600, 720, 'approved', v_user, now());
    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_other;
    ASSERT (SELECT count(*) FROM public.venue_booking_requests
            WHERE event_request_id = v_event AND status = 'cancelled') = 1,
        'AC10-N1: cancelling another event touched this one';

    -- 0071 AC9-H1 (happy): a significant change flags arrangements and reopens Confirmed
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance)
        VALUES (v_user, 'VERIFY HOTFIX confirmed', 'Confirmed', 20) RETURNING id INTO v_other;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_other, v_who, v_who);
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
            end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_other, v_day + 2, v_day + 2, 600, 720, 'approved', v_user, now())
        RETURNING id INTO v_booking;
    v_row := public.update_event_by_coordinator(v_other, v_who,
        (SELECT updated_at FROM public.event_requests WHERE id = v_other),
        '{"expected_attendance": 500}'::jsonb);
    ASSERT v_row.status = 'Planning', 'AC9-H1: a flagged change must reopen a Confirmed event';
    ASSERT EXISTS (SELECT 1 FROM public.arrangement_reviews
                   WHERE event_request_id = v_other AND arrangement_id = v_booking
                     AND trigger_type = 'event_change'),
        'AC9-H1: the booking is not flagged';
    ASSERT EXISTS (SELECT 1 FROM public.event_request_status_history
                   WHERE event_request_id = v_other AND previous_status = 'Confirmed'
                     AND new_status = 'Planning' AND source = 'event_change.no_longer_confirmed'),
        'AC9-H1: the reopening is not in the status history';
    -- AC9-P1 (partition): an ordinary edit changes the text and nothing else
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_other;
    v_count := (SELECT count(*) FROM public.arrangement_reviews WHERE event_request_id = v_other);
    v_row := public.update_event_by_coordinator(v_other, v_who,
        (SELECT updated_at FROM public.event_requests WHERE id = v_other),
        '{"purpose": "A new purpose"}'::jsonb);
    ASSERT v_row.status = 'Confirmed' AND v_row.purpose = 'A new purpose'
        AND (SELECT count(*) FROM public.arrangement_reviews WHERE event_request_id = v_other) = v_count,
        'AC9-P1: an ordinary edit must not flag or reopen';

    -- 0077 AC8-N1, AC8-N2, AC8-N3 (negative): unassigned, stale and closed events are refused
    BEGIN
        PERFORM public.update_event_by_coordinator(v_other, 'someone-else',
            (SELECT updated_at FROM public.event_requests WHERE id = v_other), '{"purpose":"x"}'::jsonb);
        RAISE EXCEPTION 'AC8-N1: unassigned edit accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    BEGIN
        PERFORM public.update_event_by_coordinator(v_other, v_who, now() - interval '10 years',
            '{"purpose":"x"}'::jsonb);
        RAISE EXCEPTION 'AC8-N2: stale edit accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    BEGIN
        PERFORM public.update_event_by_coordinator(v_event, v_who,
            (SELECT updated_at FROM public.event_requests WHERE id = v_event), '{"purpose":"x"}'::jsonb);
        RAISE EXCEPTION 'AC8-N3: edit of a cancelled event accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;

    -- 0075 AC13: venue edits flag live bookings
    -- the booking above belongs to an event at v_venue (capacity 100); it now expects 80
    UPDATE public.event_requests SET expected_attendance = 80 WHERE id = v_other;
    v_text := (SELECT status FROM public.event_requests WHERE id = v_other);
    v_count := (SELECT count(*) FROM public.arrangement_reviews WHERE trigger_type = 'venue_change');
    UPDATE public.venues SET name = 'VERIFY HOTFIX renamed' WHERE id = v_venue;
    ASSERT (SELECT count(*) FROM public.arrangement_reviews WHERE trigger_type = 'venue_change') = v_count,
        'AC13-P1: a rename must not flag anything';
    UPDATE public.venues SET max_capacity = 90 WHERE id = v_venue;
    ASSERT (SELECT count(*) FROM public.arrangement_reviews WHERE trigger_type = 'venue_change') = v_count,
        'AC13-B1: 90 still seats an event of 80';
    UPDATE public.venues SET max_capacity = 80 WHERE id = v_venue;
    ASSERT (SELECT count(*) FROM public.arrangement_reviews WHERE trigger_type = 'venue_change') = v_count,
        'AC13-B3: exactly 80 still seats an event of 80';
    UPDATE public.venues SET max_capacity = 79 WHERE id = v_venue;
    ASSERT EXISTS (SELECT 1 FROM public.arrangement_reviews
                   WHERE trigger_type = 'venue_change' AND arrangement_id = v_booking),
        'AC13-B2: 79 cannot seat an event of 80';
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
            end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_other, v_today - 5, v_today - 5, 600, 720, 'approved', v_user, now())
        RETURNING id INTO v_res;
    v_count := (SELECT count(*) FROM public.arrangement_reviews WHERE trigger_type = 'venue_change');
    UPDATE public.venues SET status = 'blocked' WHERE id = v_venue;
    ASSERT (SELECT count(*) FROM public.arrangement_reviews WHERE trigger_type = 'venue_change') > v_count,
        'AC13-H1: a blocked venue must flag its live bookings';
    ASSERT (SELECT status FROM public.venue_booking_requests WHERE id = v_booking) = 'approved'
        AND (SELECT status FROM public.event_requests WHERE id = v_other) = v_text,
        'AC13-N1: flagging must not change the booking or the event';
    -- AC13-N3 (negative): a booking that has already ended is not flagged
    ASSERT NOT EXISTS (SELECT 1 FROM public.arrangement_reviews
                       WHERE trigger_type = 'venue_change' AND arrangement_id = v_res),
        'AC13-N3: an ended booking was flagged';
    -- AC13-N2 (negative): a booking of a cancelled event is not flagged
    ASSERT NOT EXISTS (SELECT 1 FROM public.arrangement_reviews
                       WHERE trigger_type = 'venue_change' AND event_request_id = v_event),
        'AC13-N2: a cancelled event was flagged';

    -- 0074 AC12-N1 (negative): a layout capacity of zero or a non-object is refused
    BEGIN
        UPDATE public.venues SET layout_capacities = '[1]'::jsonb WHERE id = v_venue;
        RAISE EXCEPTION 'AC12-N1: non-object layout capacities accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN check_violation THEN NULL; END;

    -- 0076 AC16-H1 (happy): the email lookup returns each registration's attendee email
    INSERT INTO public.event_registrations (event_request_id, attendee_id) VALUES (v_other, v_user);
    ASSERT (SELECT count(*) FROM public.event_registration_attendee_emails(v_other)) = 1,
        'AC16-H1: the registration email is missing';
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_registration_attendee_emails(v_event)),
        'AC16-N1: another event leaked emails';

    -- 0078 AC19: Week 7 change 2 block reasons (equipment failure and other)
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY HOTFIX block venue', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_venue2;
    PERFORM public.create_venue_block(v_venue2, v_day, v_day, 420, 480, 'equipment_failure', 'Projector fault', v_user);
    PERFORM public.create_venue_block(v_venue2, v_day, v_day, 540, 600, 'other', 'Fire drill', v_user);
    ASSERT (SELECT count(*) FROM public.venue_blocks
            WHERE venue_id = v_venue2 AND reason_category IN ('equipment_failure', 'other')) = 2,
        'AC19-H1: equipment_failure and other must be accepted as block reasons';
    BEGIN
        PERFORM public.create_venue_block(v_venue2, v_day, v_day, 660, 720, 'not_a_reason', NULL, v_user);
        RAISE EXCEPTION 'AC19-N1: an unknown block reason was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN invalid_text_representation THEN NULL; END;

    -- 0079 AC20: a change request can be partly approved (Q&A #104)
    DECLARE
        v_pe uuid; v_c1 uuid; v_c2 uuid; v_c3 uuid;
    BEGIN
        INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
                venue_requirements, equipment_requirements)
            VALUES (v_user, 'VERIFY partial', 'Planning', 50, 'old venue', 'old equipment')
            RETURNING id INTO v_pe;
        INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
            VALUES (v_pe, v_who, v_who);
        INSERT INTO public.event_change_requests (event_request_id, organiser_id, explanation,
                proposed_changes, base_event_updated_at)
            VALUES (v_pe, v_user, 'more people, new rooms',
                '{"expected_attendance":60,"venue_requirements":"new venue","equipment_requirements":"new equipment"}',
                (SELECT updated_at FROM public.event_requests WHERE id = v_pe))
            RETURNING id INTO v_c1;

        -- AC20-N3 (negative): a refused field without a reason changes nothing
        BEGIN
            PERFORM public.partially_approve_event_change_request(v_pe, v_c1, v_who,
                ARRAY['expected_attendance'], '{"venue_requirements":"too small"}'::jsonb, NULL);
            RAISE EXCEPTION 'AC20-N3: a missing reason was accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        ASSERT (SELECT status FROM public.event_change_requests WHERE id = v_c1) = 'Pending'
            AND (SELECT expected_attendance FROM public.event_requests WHERE id = v_pe) = 50
            AND (SELECT jsonb_object_keys(proposed_changes) FROM public.event_change_requests
                 WHERE id = v_c1 ORDER BY 1 LIMIT 1) = 'equipment_requirements',
            'AC20-N3: a refused partial decision must leave the request as it was';
        -- AC20-N2 (negative): accepting nothing is a rejection, not a partial approval
        BEGIN
            PERFORM public.partially_approve_event_change_request(v_pe, v_c1, v_who,
                ARRAY[]::text[], '{}'::jsonb, NULL);
            RAISE EXCEPTION 'AC20-N2: accepting nothing was allowed' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        -- AC20-N1 (negative): accepting everything is an ordinary approval
        BEGIN
            PERFORM public.partially_approve_event_change_request(v_pe, v_c1, v_who,
                ARRAY['expected_attendance','venue_requirements','equipment_requirements'], '{}'::jsonb, NULL);
            RAISE EXCEPTION 'AC20-N1: accepting everything was a partial approval' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        -- AC20-N5 (negative): a field that was not proposed cannot be accepted
        BEGIN
            PERFORM public.partially_approve_event_change_request(v_pe, v_c1, v_who,
                ARRAY['registration_needs'], '{}'::jsonb, NULL);
            RAISE EXCEPTION 'AC20-N5: an unknown field was accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        -- AC20-N4 (negative): only the assigned Coordinator decides
        BEGIN
            PERFORM public.partially_approve_event_change_request(v_pe, v_c1, 'someone-else',
                ARRAY['expected_attendance'], '{"venue_requirements":"x","equipment_requirements":"y"}'::jsonb, NULL);
            RAISE EXCEPTION 'AC20-N4: another coordinator decided' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;

        -- AC20-H1 (happy): accept the attendance, refuse the other two with reasons
        PERFORM public.partially_approve_event_change_request(v_pe, v_c1, v_who,
            ARRAY['expected_attendance'],
            '{"venue_requirements":"No room for it","equipment_requirements":"Not available"}'::jsonb,
            'Only the numbers can change');
        ASSERT (SELECT status FROM public.event_change_requests WHERE id = v_c1) = 'Partially Approved',
            'AC20-H1: the request should end Partially Approved';
        ASSERT (SELECT expected_attendance FROM public.event_requests WHERE id = v_pe) = 60
            AND (SELECT venue_requirements FROM public.event_requests WHERE id = v_pe) = 'old venue'
            AND (SELECT equipment_requirements FROM public.event_requests WHERE id = v_pe) = 'old equipment',
            'AC20-H1: only the accepted field may be applied';
        ASSERT (SELECT rejected_changes -> 'venue_requirements' ->> 'reason'
                FROM public.event_change_requests WHERE id = v_c1) = 'No room for it'
            AND (SELECT rejected_changes -> 'equipment_requirements' ->> 'value'
                 FROM public.event_change_requests WHERE id = v_c1) = 'new equipment',
            'AC20-H1: each refused field keeps its value and reason';
        ASSERT (SELECT proposed_changes FROM public.event_change_requests WHERE id = v_c1)
            = '{"expected_attendance":60}'::jsonb,
            'AC20-H1: the request keeps only what was applied';
        -- AC20-N6 (negative): a decided request cannot be decided again
        BEGIN
            PERFORM public.partially_approve_event_change_request(v_pe, v_c1, v_who,
                ARRAY['expected_attendance'], '{}'::jsonb, NULL);
            RAISE EXCEPTION 'AC20-N6: a decided request was decided again' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    END;

    -- 0080 AC21: a Coordinator records the withdrawal of a request under review (Q&A #103)
    DECLARE
        v_wd uuid; v_st text;
    BEGIN
        -- AC21-B1, AC21-B2 (boundary): the three review states can be withdrawn
        FOREACH v_st IN ARRAY ARRAY['Submitted', 'Under Review', 'Changes Requested'] LOOP
            INSERT INTO public.event_requests (organiser_id, event_name, status)
                VALUES (v_user, 'VERIFY withdraw ' || v_st, v_st) RETURNING id INTO v_wd;
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
                VALUES (v_wd, v_who, v_who);
            -- AC21-N2 (negative): only the assigned Coordinator withdraws
            BEGIN
                PERFORM public.advance_event_request_by_coordinator(v_wd, 'someone-else', 'Withdrawn');
                RAISE EXCEPTION 'AC21-N2: another coordinator withdrew the request' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
            PERFORM public.advance_event_request_by_coordinator(v_wd, v_who, 'Withdrawn');
            ASSERT (SELECT status FROM public.event_requests WHERE id = v_wd) = 'Withdrawn',
                'AC21-H1: ' || v_st || ' must be withdrawable';
        END LOOP;
        -- AC21-H2 (happy): the withdrawal is recorded as its own step with who did it
        ASSERT EXISTS (SELECT 1 FROM public.event_request_status_history
                       WHERE event_request_id = v_wd AND new_status = 'Withdrawn'
                         AND source = 'coordinator.withdrawal' AND actor_id = v_who),
            'AC21-H2: the withdrawal is not in the status history';
        -- AC21-B3 (boundary): one step later (Approved) it can no longer be withdrawn
        INSERT INTO public.event_requests (organiser_id, event_name, status)
            VALUES (v_user, 'VERIFY withdraw approved', 'Approved') RETURNING id INTO v_wd;
        INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
            VALUES (v_wd, v_who, v_who);
        BEGIN
            PERFORM public.advance_event_request_by_coordinator(v_wd, v_who, 'Withdrawn');
            RAISE EXCEPTION 'AC21-B3: an approved request was withdrawn' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
        ASSERT (SELECT status FROM public.event_requests WHERE id = v_wd) = 'Approved',
            'AC21-B3: a refused withdrawal changed the status';
    END;

    -- 0081 AC22: postponing releases the arrangements and keeps the event (Q&A #69, #121)
    DECLARE
        v_pe uuid; v_pv uuid; v_pb uuid; v_ph uuid; v_pq uuid; v_pr uuid; v_pg uuid;
    BEGIN
        INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
                proposed_date_times, registration_capacity)
            VALUES (v_user, 'VERIFY postpone', 'Confirmed', 20, ARRAY[now() + interval '20 days'], 5)
            RETURNING id INTO v_pe;
        INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
            VALUES (v_pe, v_who, v_who);
        INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
                supported_layouts, operating_slots)
            VALUES ('VERIFY postpone venue', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
            RETURNING id INTO v_pv;
        INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
                end_date, start_minute, end_minute, status, decided_by, decided_at)
            VALUES (v_pv, v_user, v_pe, v_day + 5, v_day + 5, 600, 720, 'approved', v_user, now())
            RETURNING id INTO v_pb;
        INSERT INTO public.venue_holds (venue_id, event_request_id, start_date, end_date, start_minute,
                end_minute, expires_at, placed_by)
            VALUES (v_pv, v_pe, v_day + 6, v_day + 6, 600, 720, now() + interval '2 days', v_user)
            RETURNING id INTO v_ph;
        INSERT INTO public.equipment (type, total_owned_quantity, home_location, operational_status)
            VALUES ('VERIFY postpone kit', 5, 'Test wing', 'AVAILABLE') RETURNING id INTO v_pg;
        INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
            VALUES (v_pe, 'VERIFY postpone kit', 2, v_user) RETURNING id INTO v_pq;
        INSERT INTO public.equipment_reservations (equipment_id, event_request_id, requirement_id,
                quantity, collection_date, return_date, created_by)
            VALUES (v_pg, v_pe, v_pq, 2, v_day + 4, v_day + 5, v_user) RETURNING id INTO v_pr;
        INSERT INTO public.event_registrations (event_request_id, attendee_id) VALUES (v_pe, v_user);

        -- AC22-N1 (negative): a postponement needs a reason and changes nothing without one
        BEGIN
            PERFORM public.postpone_event_by_coordinator(v_pe, v_who, '  ');
            RAISE EXCEPTION 'AC22-N1: a reasonless postponement was accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        ASSERT (SELECT status FROM public.event_requests WHERE id = v_pe) = 'Confirmed'
            AND (SELECT status FROM public.venue_booking_requests WHERE id = v_pb) = 'approved',
            'AC22-N1: a refused postponement changed something';
        -- AC22-N3 (negative): only the assigned Coordinator postpones
        BEGIN
            PERFORM public.postpone_event_by_coordinator(v_pe, 'someone-else', 'Venue unavailable');
            RAISE EXCEPTION 'AC22-N3: another coordinator postponed the event' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
        -- AC22-N2 (negative): a request that is not yet approved is not postponed
        DECLARE v_early uuid;
        BEGIN
            INSERT INTO public.event_requests (organiser_id, event_name, status)
                VALUES (v_user, 'VERIFY postpone early', 'Submitted') RETURNING id INTO v_early;
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
                VALUES (v_early, v_who, v_who);
            BEGIN
                PERFORM public.postpone_event_by_coordinator(v_early, v_who, 'x');
                RAISE EXCEPTION 'AC22-N2: a submitted request was postponed' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
        END;

        -- AC22-H1 (happy): postponing with no new date releases bookings, holds and reservations
        PERFORM public.postpone_event_by_coordinator(v_pe, v_who, 'Venue unavailable on the day');
        ASSERT (SELECT status FROM public.event_requests WHERE id = v_pe) = 'Postponed',
            'AC22-H1: the event should be Postponed';
        ASSERT (SELECT status FROM public.venue_booking_requests WHERE id = v_pb) = 'cancelled'
            AND (SELECT status FROM public.venue_holds WHERE id = v_ph) = 'released'
            AND NOT EXISTS (SELECT 1 FROM public.equipment_reservations WHERE event_request_id = v_pe)
            AND (SELECT reason FROM public.equipment_reservation_releases WHERE reservation_id = v_pr)
                = 'Event postponed',
            'AC22-H1: bookings, holds and reservations should all be released';
        -- AC22-H2 (happy): the record, requirement, registration and reason are kept
        ASSERT EXISTS (SELECT 1 FROM public.equipment_requirements WHERE id = v_pq)
            AND EXISTS (SELECT 1 FROM public.event_registrations WHERE event_request_id = v_pe)
            AND (SELECT reason FROM public.event_postponements
                 WHERE event_request_id = v_pe AND resumed_at IS NULL) = 'Venue unavailable on the day'
            AND (SELECT previous_status FROM public.event_postponements
                 WHERE event_request_id = v_pe) = 'Confirmed',
            'AC22-H2: the postponed event should keep its record, requirement and registration';
        -- AC22-N6 (negative): a postponed event cannot take a venue booking back
        BEGIN
            PERFORM public.create_event_venue_booking_request(jsonb_build_object(
                'id', gen_random_uuid(), 'venue_id', v_pv, 'event_request_id', v_pe,
                'requested_by', v_user, 'start_date', v_day + 12, 'end_date', v_day + 12,
                'start_minute', 600, 'end_minute', 720, 'status', 'pending'),
                (SELECT updated_at FROM public.event_requests WHERE id = v_pe));
            RAISE EXCEPTION 'AC22-N6: a postponed event took a venue booking' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
        -- AC22-N4 (negative): a postponed event cannot be postponed again
        BEGIN
            PERFORM public.postpone_event_by_coordinator(v_pe, v_who, 'again');
            RAISE EXCEPTION 'AC22-N4: postponed twice' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;

        -- AC22-B1, AC22-B2 (boundary): a new date in the past or none is refused, a future one accepted
        BEGIN
            PERFORM public.resume_postponed_event(v_pe, v_who, ARRAY[now() - interval '1 minute']);
            RAISE EXCEPTION 'AC22-B1: a past date was accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        BEGIN
            PERFORM public.resume_postponed_event(v_pe, v_who, ARRAY[]::timestamptz[]);
            RAISE EXCEPTION 'AC22-B2: no date was accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        ASSERT (SELECT status FROM public.event_requests WHERE id = v_pe) = 'Postponed',
            'AC22-B1: a refused resume changed the status';
        v_row := public.resume_postponed_event(v_pe, v_who, ARRAY[now() + interval '40 days']);
        ASSERT v_row.status = 'Planning' AND v_row.proposed_date_times[1] > now() + interval '39 days',
            'AC22-H3: resuming returns the event to Planning on the new date';
        ASSERT (SELECT resumed_by FROM public.event_postponements WHERE event_request_id = v_pe) = v_who
            AND (SELECT count(*) FROM public.event_request_status_history
                 WHERE event_request_id = v_pe AND new_status = 'Postponed') = 1,
            'AC22-H3: the resume is recorded';
        -- AC22-N5 (negative): only a postponed event is resumed
        BEGIN
            PERFORM public.resume_postponed_event(v_pe, v_who, ARRAY[now() + interval '50 days']);
            RAISE EXCEPTION 'AC22-N5: a planning event was resumed' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
        -- AC22-X1 (cross-cutting): a postponed event can still be cancelled
        PERFORM public.postpone_event_by_coordinator(v_pe, v_who, 'Second postponement');
        PERFORM public.advance_event_request_by_coordinator(v_pe, v_who, 'Cancelled');
        ASSERT (SELECT status FROM public.event_requests WHERE id = v_pe) = 'Cancelled',
            'AC22-X1: a postponed event should be cancellable';
    END;

    -- 0082 AC23: a VIP can be added above the registration capacity, up to the venue (Q&A #99)
    DECLARE
        v_ve uuid; v_ve2 uuid; v_vv uuid; v_u2 uuid; v_u3 uuid; v_m2 text; v_m3 text;
    BEGIN
        SELECT id, email INTO v_u2, v_m2 FROM auth.users ORDER BY created_at, id OFFSET 1 LIMIT 1;
        SELECT id, email INTO v_u3, v_m3 FROM auth.users ORDER BY created_at, id OFFSET 2 LIMIT 1;
        IF v_u3 IS NULL THEN
            RAISE NOTICE 'AC23 skipped: it needs three users in auth.users';
        ELSE
            INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity)
                VALUES (v_user, 'VERIFY vip', 'Confirmed', 1) RETURNING id INTO v_ve;
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
                VALUES (v_ve, v_who, v_who);
            INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
                    supported_layouts, operating_slots)
                VALUES ('VERIFY vip venue', 'Test wing', 2, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
                RETURNING id INTO v_vv;
            INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
                    end_date, start_minute, end_minute, status, decided_by, decided_at)
                VALUES (v_vv, v_user, v_ve, v_day + 8, v_day + 8, 600, 720, 'approved', v_user, now());
            INSERT INTO public.event_registrations (event_request_id, attendee_id) VALUES (v_ve, v_user);

            -- AC23-H1 (happy): full at the registration capacity (1) but the venue seats 2
            PERFORM public.coordinator_register_attendee(v_ve, v_who, v_m2);
            ASSERT (SELECT count(*) FROM public.event_registrations
                    WHERE event_request_id = v_ve AND status = 'Registered') = 2,
                'AC23-H1: a VIP should be added above the registration capacity';
            -- AC23-B1 (boundary): the places now equal the venue capacity, so one more is refused
            BEGIN
                PERFORM public.coordinator_register_attendee(v_ve, v_who, v_m3);
                RAISE EXCEPTION 'AC23-B1: the venue capacity was exceeded' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
            ASSERT (SELECT count(*) FROM public.event_registrations
                    WHERE event_request_id = v_ve AND status = 'Registered') = 2,
                'AC23-B1: a refused VIP changed the registrations';
            -- AC23-N1 (negative): with no approved venue there is no venue capacity to go above
            INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity)
                VALUES (v_user, 'VERIFY vip no venue', 'Confirmed', 1) RETURNING id INTO v_ve2;
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
                VALUES (v_ve2, v_who, v_who);
            INSERT INTO public.event_registrations (event_request_id, attendee_id) VALUES (v_ve2, v_user);
            BEGIN
                PERFORM public.coordinator_register_attendee(v_ve2, v_who, v_m2);
                RAISE EXCEPTION 'AC23-N1: a VIP went above capacity with no venue' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
            -- AC23-N2 (negative): a cancelled booking is not venue capacity
            UPDATE public.venue_booking_requests SET status = 'cancelled', cancelled_by = v_user,
                cancelled_at = now() WHERE event_request_id = v_ve;
            BEGIN
                PERFORM public.coordinator_register_attendee(v_ve, v_who, v_m3);
                RAISE EXCEPTION 'AC23-N2: a cancelled booking still counted as capacity' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
        END IF;
    END;

    -- 0083 AC24: the assigned Coordinator changes the Event Organiser (Q&A #59, #61)
    DECLARE
        v_oe uuid; v_oe2 uuid; v_u2 uuid; v_m2 text; v_m3 text; v_org uuid; v_cr uuid;
    BEGIN
        SELECT id, email INTO v_u2, v_m2 FROM auth.users ORDER BY created_at, id OFFSET 1 LIMIT 1;
        SELECT email INTO v_m3 FROM auth.users ORDER BY created_at, id OFFSET 2 LIMIT 1;
        IF v_m3 IS NULL THEN
            RAISE NOTICE 'AC24 skipped: it needs three users in auth.users';
        ELSE
            UPDATE auth.users SET raw_app_meta_data = '{"role":"event_organiser"}' WHERE id = v_u2;
            INSERT INTO public.event_requests (organiser_id, event_name, status)
                VALUES (v_user, 'VERIFY organiser', 'Planning') RETURNING id INTO v_oe;
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
                VALUES (v_oe, v_who, v_who);
            INSERT INTO public.event_change_requests (event_request_id, organiser_id, explanation,
                    proposed_changes, base_event_updated_at)
                VALUES (v_oe, v_user, 'more people', '{"expected_attendance":9}',
                    (SELECT updated_at FROM public.event_requests WHERE id = v_oe))
                RETURNING id INTO v_cr;

            -- AC24-N1 (negative): an email nobody has is refused
            BEGIN
                PERFORM public.change_event_organiser(v_oe, v_who, 'nobody@example.test', 'left');
                RAISE EXCEPTION 'AC24-N1: an unknown email was accepted' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0006' THEN NULL; END;
            -- AC24-N2 (negative): a person who is not an Event Organiser is refused
            BEGIN
                PERFORM public.change_event_organiser(v_oe, v_who, v_m3, 'left');
                RAISE EXCEPTION 'AC24-N2: a non-organiser was made organiser' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0006' THEN NULL; END;
            -- AC24-N3 (negative): the current Organiser cannot be "changed" to themselves
            UPDATE auth.users SET raw_app_meta_data = '{"role":"event_organiser"}' WHERE id = v_user;
            BEGIN
                PERFORM public.change_event_organiser(v_oe, v_who,
                    (SELECT email FROM auth.users WHERE id = v_user), 'same');
                RAISE EXCEPTION 'AC24-N3: changed to the same organiser' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
            -- AC24-N4 (negative): a reason is required
            BEGIN
                PERFORM public.change_event_organiser(v_oe, v_who, v_m2, '  ');
                RAISE EXCEPTION 'AC24-N4: a reasonless change was accepted' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
            -- AC24-N5 (negative): only the assigned Coordinator changes the Organiser
            BEGIN
                PERFORM public.change_event_organiser(v_oe, 'someone-else', v_m2, 'left');
                RAISE EXCEPTION 'AC24-N5: another coordinator changed the organiser' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
            ASSERT (SELECT organiser_id FROM public.event_requests WHERE id = v_oe) = v_user
                AND NOT EXISTS (SELECT 1 FROM public.event_organiser_changes WHERE event_request_id = v_oe),
                'AC24-N1..N5: a refused change altered the event or left an audit row';

            -- AC24-H1 (happy): the Organiser changes, the audit row is kept, a pending change follows
            PERFORM public.change_event_organiser(v_oe, v_who, v_m2, 'Account deactivated');
            ASSERT (SELECT organiser_id FROM public.event_requests WHERE id = v_oe) = v_u2,
                'AC24-H1: the organiser should now be the new person';
            ASSERT (SELECT previous_organiser_id FROM public.event_organiser_changes
                    WHERE event_request_id = v_oe) = v_user
                AND (SELECT reason FROM public.event_organiser_changes
                     WHERE event_request_id = v_oe) = 'Account deactivated',
                'AC24-H1: the change is not recorded with who it was from and why';
            ASSERT (SELECT organiser_id FROM public.event_change_requests WHERE id = v_cr) = v_u2,
                'AC24-H2: a pending change request should follow the new organiser';

            -- AC24-N6 (negative): not for a cancelled event
            INSERT INTO public.event_requests (organiser_id, event_name, status)
                VALUES (v_user, 'VERIFY organiser cancelled', 'Cancelled') RETURNING id INTO v_oe2;
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
                VALUES (v_oe2, v_who, v_who);
            BEGIN
                PERFORM public.change_event_organiser(v_oe2, v_who, v_m2, 'left');
                RAISE EXCEPTION 'AC24-N6: a cancelled event changed organiser' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;

            -- AC24-N7, AC24-H3: with a client organisation, only a member of it can take over
            INSERT INTO public.client_organisations (name) VALUES ('VERIFY client') RETURNING id INTO v_org;
            INSERT INTO public.organisation_members (user_id, organisation_id) VALUES (v_user, v_org);
            INSERT INTO public.event_requests (organiser_id, event_name, status)
                VALUES (v_user, 'VERIFY organiser org', 'Planning') RETURNING id INTO v_oe2;
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
                VALUES (v_oe2, v_who, v_who);
            ASSERT (SELECT organisation_id FROM public.event_requests WHERE id = v_oe2) = v_org,
                'AC24-N7: the fixture event should belong to the organisation';
            BEGIN
                PERFORM public.change_event_organiser(v_oe2, v_who, v_m2, 'left');
                RAISE EXCEPTION 'AC24-N7: someone outside the organisation took over' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0007' THEN NULL; END;
            INSERT INTO public.organisation_members (user_id, organisation_id) VALUES (v_u2, v_org);
            PERFORM public.change_event_organiser(v_oe2, v_who, v_m2, 'left');
            ASSERT (SELECT organiser_id FROM public.event_requests WHERE id = v_oe2) = v_u2
                AND (SELECT organisation_id FROM public.event_requests WHERE id = v_oe2) = v_org,
                'AC24-H3: a colleague in the organisation takes over and the event keeps its organisation';
        END IF;
    END;

    -- 0084 AC25: an equipment requirement can be marked not essential (Q&A #80, #106)
    DECLARE
        v_ee uuid; v_ev uuid; v_eq uuid; v_er public.equipment_requirements;
    BEGIN
        INSERT INTO public.event_requests (organiser_id, event_name, status)
            VALUES (v_user, 'VERIFY essential', 'Planning') RETURNING id INTO v_ee;
        INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
            VALUES (v_ee, v_who, v_who);
        INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
                supported_layouts, operating_slots)
            VALUES ('VERIFY essential venue', 'Test wing', 50, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
            RETURNING id INTO v_ev;
        INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
                end_date, start_minute, end_minute, status, decided_by, decided_at)
            VALUES (v_ev, v_user, v_ee, v_day + 9, v_day + 9, 600, 720, 'approved', v_user, now());
        INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
            VALUES (v_ee, 'VERIFY optional kit', 3, v_user) RETURNING id INTO v_eq;

        -- AC25-H1 (happy): a requirement is essential unless said otherwise, and blocks the safety review
        ASSERT (SELECT essential FROM public.equipment_requirements WHERE id = v_eq),
            'AC25-H1: a requirement should be essential by default';
        ASSERT private.event_readiness_issues(v_ee) @> jsonb_build_array(
                jsonb_build_object('kind', 'equipment_not_reserved', 'requirement_id', v_eq,
                                   'equipment_type', 'VERIFY optional kit', 'required', 3, 'reserved', 0)),
            'AC25-H1: an unreserved essential requirement must be listed as outstanding';
        BEGIN
            PERFORM public.send_event_request_for_safety_review(v_ee, v_who);
            RAISE EXCEPTION 'AC25-H1: sent for safety review with an essential requirement unreserved'
                USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0005' THEN NULL; END;

        -- AC25-N1 (negative): marking not essential needs a note, and changes nothing without one
        BEGIN
            PERFORM public.set_requirement_essential(v_eq, v_user, false, '  ');
            RAISE EXCEPTION 'AC25-N1: no note was accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
        -- AC25-N2 (negative): only the assigned Coordinator decides
        BEGIN
            PERFORM public.set_requirement_essential(v_eq, gen_random_uuid(), false, 'agreed with support');
            RAISE EXCEPTION 'AC25-N2: another coordinator decided' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
        -- AC25-N3 (negative): an unknown requirement
        BEGIN
            PERFORM public.set_requirement_essential(gen_random_uuid(), v_user, false, 'x');
            RAISE EXCEPTION 'AC25-N3: an unknown requirement was accepted' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
        ASSERT (SELECT essential FROM public.equipment_requirements WHERE id = v_eq),
            'AC25-N1..N3: a refused change altered the requirement';

        -- AC25-H2 (happy): not essential, so it no longer blocks, and the note is kept
        v_er := public.set_requirement_essential(v_eq, v_user, false, 'Support will bring one on the day');
        ASSERT NOT v_er.essential AND v_er.essential_note = 'Support will bring one on the day'
            AND v_er.essential_set_by = v_user,
            'AC25-H2: the decision and its note should be recorded';
        ASSERT NOT (private.event_readiness_issues(v_ee) @> jsonb_build_array(
                jsonb_build_object('kind', 'equipment_not_reserved', 'requirement_id', v_eq,
                                   'equipment_type', 'VERIFY optional kit', 'required', 3, 'reserved', 0))),
            'AC25-H2: a not-essential requirement must not be outstanding';
        PERFORM public.send_event_request_for_safety_review(v_ee, v_who);
        ASSERT (SELECT status FROM public.event_requests WHERE id = v_ee) = 'Safety Review',
            'AC25-H2: the event should go to safety review with only a non-essential gap';
        -- AC25-H3 (happy): marking it essential again puts it back in the check
        v_er := public.set_requirement_essential(v_eq, v_user, true, NULL);
        ASSERT v_er.essential AND v_er.essential_note IS NULL
            AND private.event_readiness_issues(v_ee) @> jsonb_build_array(
                jsonb_build_object('kind', 'equipment_not_reserved', 'requirement_id', v_eq,
                                   'equipment_type', 'VERIFY optional kit', 'required', 3, 'reserved', 0)),
            'AC25-H3: an essential requirement is outstanding again';
        -- AC25-N4 (negative): a closed event's requirements are not changed
        UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_ee;
        BEGIN
            PERFORM public.set_requirement_essential(v_eq, v_user, false, 'late');
            RAISE EXCEPTION 'AC25-N4: a closed event was changed' USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    END;

    RAISE NOTICE 'ALL RELEASE 1 HOTFIX VERIFICATIONS PASSED';
END $$;

ROLLBACK;
