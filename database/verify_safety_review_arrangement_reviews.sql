-- Run after 0045_safety_review_arrangement_reviews.sql (SCRUM-60 increment 2b),
-- which needs SCRUM-64's 0030-0040. Every change is rolled back.
-- Borrows the oldest auth user as organiser and Safety Officer.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_safety_review_arrangement_reviews.sql

BEGIN;

-- AC6-X7 fault seam: fail the arrangement-review insert for one marked reason.
CREATE FUNCTION pg_temp.scrum60_fail_flag() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.reason = 'SCRUM60 injected flag failure' THEN
        RAISE EXCEPTION 'SCRUM60 injected flag failure' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER scrum60_fail_flag BEFORE INSERT ON public.arrangement_reviews
    FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum60_fail_flag();

DO $$
DECLARE
    v_officer uuid;
    v_today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
    v_venue uuid;
    v_event uuid;
    v_other_event uuid;
    v_booking uuid;
    v_other_booking uuid;
    v_review uuid;
    v_status text;
    v_count int;
    v_detail text;
    v_reason text := 'Recheck emergency exits for 300 people.';
BEGIN
    SELECT id INTO v_officer FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_officer IS NULL THEN
        RAISE EXCEPTION 'Needs at least one auth user';
    END IF;
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_officer, 'safety_officer')
        ON CONFLICT DO NOTHING;
    INSERT INTO public.venues (name, location, max_capacity, facilities,
            accessibility_features, supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM60 venue', 'Test wing', 400, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM']::public.booking_slot[])
        RETURNING id INTO v_venue;

    -- AC4c-X1: changes_requested flags each target with the saved decision id
    -- and reason, and enqueues its notice, in the same transaction.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 flags', 'Safety Review') RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status)
        VALUES (v_venue, v_officer, v_event, v_today + 7, v_today + 7,
            ARRAY['AM']::public.booking_slot[], 'pending') RETURNING id INTO v_booking;
    PERFORM public.decide_safety_review(v_event, v_officer, 'changes_requested', v_reason,
        jsonb_build_array(jsonb_build_object('arrangement', 'venue_booking', 'id', v_booking)));
    SELECT id INTO v_review FROM public.safety_reviews WHERE event_request_id = v_event;
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    IF v_status <> 'Planning' THEN
        RAISE EXCEPTION 'AC4c-X1: expected Planning, got %', v_status;
    END IF;
    SELECT count(*) INTO v_count FROM public.arrangement_reviews
        WHERE event_request_id = v_event AND arrangement = 'venue_booking'
          AND arrangement_id = v_booking AND trigger_type = 'safety_recheck'
          AND trigger_id = v_review AND reason = v_reason AND cleared_at IS NULL;
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'AC4c-X1: expected one linked flag, got %', v_count;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.arrangement_review_notification_outbox o
                   JOIN public.arrangement_reviews r ON r.id = o.review_id
                   WHERE r.trigger_id = v_review) THEN
        RAISE EXCEPTION 'AC4c-X1: flag notice not enqueued';
    END IF;

    -- AC6-X6: approval is refused while that flag is outstanding (P0005 with the
    -- item listed), and nothing is written.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 blocked', 'Safety Review') RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status, cancelled_by, cancelled_at)
        VALUES (v_venue, v_officer, v_event, v_today + 8, v_today + 8,
            ARRAY['AM']::public.booking_slot[], 'cancelled', v_officer, now())
        RETURNING id INTO v_booking;
    INSERT INTO public.arrangement_reviews (event_request_id, arrangement, arrangement_id,
            trigger_id, trigger_type, changed_fields, reason)
        VALUES (v_event, 'venue_booking', v_booking, gen_random_uuid(), 'event_change',
            '{expected_attendance}', 'Attendance changed.');
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
        RAISE EXCEPTION 'AC6-X6: approved with an outstanding review';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN
        GET STACKED DIAGNOSTICS v_detail = PG_EXCEPTION_DETAIL;
    END;
    IF v_detail::jsonb -> 0 ->> 'kind' <> 'arrangement_needs_review'
       OR (v_detail::jsonb -> 0 ->> 'arrangement_id')::uuid <> v_booking THEN
        RAISE EXCEPTION 'AC6-X6: unexpected detail %', v_detail;
    END IF;
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    SELECT count(*) INTO v_count FROM public.safety_reviews WHERE event_request_id = v_event;
    IF v_status <> 'Safety Review' OR v_count <> 0 THEN
        RAISE EXCEPTION 'AC6-X6: refused approval changed % / % reviews', v_status, v_count;
    END IF;

    -- AC6-X8: a cleared review no longer blocks approval.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 cleared', 'Safety Review') RETURNING id INTO v_event;
    INSERT INTO public.arrangement_reviews (event_request_id, arrangement, arrangement_id,
            trigger_id, trigger_type, changed_fields, reason, cleared_at, cleared_by)
        VALUES (v_event, 'venue_booking', gen_random_uuid(), gen_random_uuid(), 'event_change',
            '{expected_attendance}', 'Attendance changed.', now(), v_officer);
    PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    IF v_status <> 'Confirmed' THEN
        RAISE EXCEPTION 'AC6-X8: expected Confirmed, got %', v_status;
    END IF;

    -- AC4c-X2: a target from another event is invalid input (22023), and the
    -- decision, status and flags all roll back.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 other', 'Planning') RETURNING id INTO v_other_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status)
        VALUES (v_venue, v_officer, v_other_event, v_today + 9, v_today + 9,
            ARRAY['AM']::public.booking_slot[], 'pending') RETURNING id INTO v_other_booking;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 cross-event', 'Safety Review') RETURNING id INTO v_event;
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'changes_requested', v_reason,
            jsonb_build_array(jsonb_build_object('arrangement', 'venue_booking', 'id', v_other_booking)));
        RAISE EXCEPTION 'AC4c-X2: cross-event target accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    SELECT count(*) INTO v_count FROM public.safety_reviews WHERE event_request_id = v_event;
    IF v_status <> 'Safety Review' OR v_count <> 0
       OR EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE arrangement_id = v_other_booking) THEN
        RAISE EXCEPTION 'AC4c-X2: refused decision left % / % reviews or a flag', v_status, v_count;
    END IF;

    -- AC6-X7: if writing a flag fails, the decision and status roll back too.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'VERIFY SCRUM60 fault', 'Safety Review') RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status)
        VALUES (v_venue, v_officer, v_event, v_today + 10, v_today + 10,
            ARRAY['AM']::public.booking_slot[], 'pending') RETURNING id INTO v_booking;
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'changes_requested',
            'SCRUM60 injected flag failure',
            jsonb_build_array(jsonb_build_object('arrangement', 'venue_booking', 'id', v_booking)));
        RAISE EXCEPTION 'AC6-X7: injected failure did not abort the decision';
    EXCEPTION WHEN SQLSTATE '23514' THEN NULL;
    END;
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    SELECT count(*) INTO v_count FROM public.safety_reviews WHERE event_request_id = v_event;
    IF v_status <> 'Safety Review' OR v_count <> 0 THEN
        RAISE EXCEPTION 'AC6-X7: failed flag left % / % reviews', v_status, v_count;
    END IF;

    RAISE NOTICE 'ALL SCRUM-60 ARRANGEMENT REVIEW VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
