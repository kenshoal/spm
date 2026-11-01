-- Run after 0069 to 0077 (Release 1 hotfixes 3, 4, 8 to 13, 16). Every change is
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

    RAISE NOTICE 'ALL RELEASE 1 HOTFIX VERIFICATIONS PASSED';
END $$;

ROLLBACK;
