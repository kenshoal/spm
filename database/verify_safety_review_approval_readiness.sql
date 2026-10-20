-- Run after 0047_safety_review_approval_readiness.sql (SCRUM-60), which needs
-- SCRUM-58's 0046 and SCRUM-64's 0030-0040. Every change is rolled back.
-- Borrows the oldest auth user as organiser and Safety Officer.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_safety_review_approval_readiness.sql

BEGIN;

DO $$
DECLARE
    v_officer uuid;
    v_today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
    v_venue uuid;
    v_event uuid;
    v_booking uuid;
    v_equipment uuid;
    v_requirement uuid;
    v_status text;
    v_count int;
    v_detail jsonb;
BEGIN
    SELECT id INTO v_officer FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_officer IS NULL THEN
        RAISE EXCEPTION 'Needs at least one auth user';
    END IF;
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_officer, 'safety_officer')
        ON CONFLICT DO NOTHING;
    INSERT INTO public.venues (name, location, max_capacity, facilities,
            accessibility_features, supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM60 readiness venue', 'Test wing', 400, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM']::public.booking_slot[])
        RETURNING id INTO v_venue;
    INSERT INTO public.equipment (type, total_owned_quantity, home_location, created_by)
        VALUES ('VERIFY SCRUM60 microphone', 10, 'Test store', v_officer)
        RETURNING id INTO v_equipment;

    -- AC6-X9: no booking at all → refused with no_venue_booking; nothing written.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 no booking', 'Safety Review') RETURNING id INTO v_event;
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
        RAISE EXCEPTION 'AC6-X9: approved an event with no booking';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN
        GET STACKED DIAGNOSTICS v_detail = PG_EXCEPTION_DETAIL;
    END;
    IF v_detail <> '[{"kind": "no_venue_booking"}]'::jsonb THEN
        RAISE EXCEPTION 'AC6-X9: unexpected detail %', v_detail;
    END IF;
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    SELECT count(*) INTO v_count FROM public.safety_reviews WHERE event_request_id = v_event;
    IF v_status <> 'Safety Review' OR v_count <> 0 THEN
        RAISE EXCEPTION 'AC6-X9: refused approval changed % / % reviews', v_status, v_count;
    END IF;

    -- AC6-X10: readiness items come first, then review flags: an approved booking,
    -- an equipment shortfall (2 of 4) and an outstanding flag.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 short', 'Safety Review') RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status, decided_by, decided_at)
        VALUES (v_venue, v_officer, v_event, v_today + 7, v_today + 7,
            ARRAY['AM']::public.booking_slot[], 'approved', v_officer, now())
        RETURNING id INTO v_booking;
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
        VALUES (v_event, 'VERIFY SCRUM60 microphone', 4, v_officer) RETURNING id INTO v_requirement;
    INSERT INTO public.equipment_reservations (equipment_id, requirement_id, event_request_id,
            quantity, collection_date, return_date, created_by)
        VALUES (v_equipment, v_requirement, v_event, 2, v_today + 6, v_today + 8, v_officer);
    INSERT INTO public.arrangement_reviews (event_request_id, arrangement, arrangement_id,
            trigger_id, trigger_type, changed_fields, reason)
        VALUES (v_event, 'venue_booking', v_booking, gen_random_uuid(), 'event_change',
            '{expected_attendance}', 'Attendance changed.');
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
        RAISE EXCEPTION 'AC6-X10: approved an unready, flagged event';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN
        GET STACKED DIAGNOSTICS v_detail = PG_EXCEPTION_DETAIL;
    END;
    IF jsonb_array_length(v_detail) <> 2
       OR v_detail -> 0 ->> 'kind' <> 'equipment_not_reserved'
       OR (v_detail -> 0 ->> 'reserved')::int <> 2 OR (v_detail -> 0 ->> 'required')::int <> 4
       OR v_detail -> 1 ->> 'kind' <> 'arrangement_needs_review'
       OR (v_detail -> 1 ->> 'arrangement_id')::uuid <> v_booking THEN
        RAISE EXCEPTION 'AC6-X10: unexpected detail %', v_detail;
    END IF;
    SELECT count(*) INTO v_count FROM public.safety_reviews WHERE event_request_id = v_event;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC6-X10: refused approval wrote % reviews', v_count;
    END IF;

    -- AC6-X11: asking for changes is still allowed on an unready event.
    PERFORM public.decide_safety_review(v_event, v_officer, 'changes_requested',
        'Reserve the other two microphones.', '[]');
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    IF v_status <> 'Planning' THEN
        RAISE EXCEPTION 'AC6-X11: expected Planning, got %', v_status;
    END IF;

    -- AC6-X13 (review of PR #62): the same arrangement listed twice is refused
    -- with 22023 before any write.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 duplicate', 'Safety Review') RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status, decided_by, decided_at)
        VALUES (v_venue, v_officer, v_event, v_today + 12, v_today + 12,
            ARRAY['AM']::public.booking_slot[], 'approved', v_officer, now())
        RETURNING id INTO v_booking;
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'changes_requested', 'Recheck.',
            jsonb_build_array(
                jsonb_build_object('arrangement', 'venue_booking', 'id', v_booking),
                jsonb_build_object('arrangement', 'venue_booking', 'id', upper(v_booking::text))));
        RAISE EXCEPTION 'AC6-X13: duplicate targets accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    SELECT count(*) INTO v_count FROM public.safety_reviews WHERE event_request_id = v_event;
    IF v_count <> 0 OR EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE event_request_id = v_event) THEN
        RAISE EXCEPTION 'AC6-X13: duplicate targets wrote a review or flag';
    END IF;

    -- AC6-X12: a ready event with nothing outstanding is approved.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 ready', 'Safety Review') RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status, decided_by, decided_at)
        VALUES (v_venue, v_officer, v_event, v_today + 9, v_today + 9,
            ARRAY['AM']::public.booking_slot[], 'approved', v_officer, now());
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
        VALUES (v_event, 'VERIFY SCRUM60 microphone', 2, v_officer) RETURNING id INTO v_requirement;
    INSERT INTO public.equipment_reservations (equipment_id, requirement_id, event_request_id,
            quantity, collection_date, return_date, created_by)
        VALUES (v_equipment, v_requirement, v_event, 2, v_today + 8, v_today + 10, v_officer);
    PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    IF v_status <> 'Confirmed' THEN
        RAISE EXCEPTION 'AC6-X12: expected Confirmed, got %', v_status;
    END IF;

    RAISE NOTICE 'ALL SCRUM-60 APPROVAL READINESS VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
