-- Run after 0034_safety_review_decisions.sql and 0044_safety_review_null_inputs.sql
-- (SCRUM-60 increment 2).
-- Every change is rolled back. Borrows the oldest auth user as organiser and
-- Safety Officer, and the oldest user without that role as the non-officer.
-- Uses no DELETE or UPDATE, so the Supabase MCP runs it without a confirmation.

BEGIN;

DO $$
DECLARE
    v_officer uuid;
    v_other uuid;
    v_event uuid;
    v_status text;
    v_reviews int;
    v_targets jsonb;
    v_venue uuid;
    v_booking uuid;
    v_bad record;
BEGIN
    SELECT id INTO v_officer FROM auth.users ORDER BY created_at LIMIT 1;
    SELECT u.id INTO v_other FROM auth.users u
        WHERE u.id <> v_officer
          AND NOT EXISTS (SELECT 1 FROM public.staff_roles s
                          WHERE s.user_id = u.id AND s.role = 'safety_officer')
        ORDER BY u.created_at LIMIT 1;
    IF v_other IS NULL THEN
        RAISE EXCEPTION 'Needs a second auth user without the safety_officer role';
    END IF;
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_officer, 'safety_officer')
        ON CONFLICT DO NOTHING;
    INSERT INTO public.venues (name, location, max_capacity, facilities,
            accessibility_features, supported_layouts, operating_slots)
        VALUES ('verify SCRUM-60 venue', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM']::public.booking_slot[])
        RETURNING id INTO v_venue;

    -- AC3-X1: approval confirms, records the review and the history actor.
    -- The event is ready (one approved booking), so this also holds from 0047.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'verify SCRUM-60 approve', 'Safety Review')
        RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status, decided_by, decided_at)
        VALUES (v_venue, v_officer, v_event, current_date + 6, current_date + 6,
            ARRAY['AM']::public.booking_slot[], 'approved', v_officer, now());
    PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    IF v_status <> 'Confirmed' THEN
        RAISE EXCEPTION 'AC3-X1: expected Confirmed, got %', v_status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.safety_reviews
                   WHERE event_request_id = v_event AND decision = 'approved'
                     AND decided_by = v_officer) THEN
        RAISE EXCEPTION 'AC3-X1: review row missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.event_request_status_history
                   WHERE event_request_id = v_event AND previous_status = 'Safety Review'
                     AND new_status = 'Confirmed' AND actor_id = v_officer::text
                     AND actor_role = 'safety_officer' AND source = 'safety.approval') THEN
        RAISE EXCEPTION 'AC3-X1: history row missing';
    END IF;

    -- AC6-X3: a repeated decision is refused once the event has left Safety Review.
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
        RAISE EXCEPTION 'AC6-X3: repeated decision accepted';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    -- AC4a-X1: changes_requested returns to Planning and keeps reason and targets.
    -- The target is a real booking of this event, so the check also holds once
    -- 0045 validates target membership (Heng Rui, message 2213).
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'verify SCRUM-60 changes', 'Safety Review')
        RETURNING id INTO v_event;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
            start_date, end_date, slots, status)
        VALUES (v_venue, v_officer, v_event, current_date + 7, current_date + 7,
            ARRAY['AM']::public.booking_slot[], 'pending')
        RETURNING id INTO v_booking;
    v_targets := jsonb_build_array(
        jsonb_build_object('arrangement', 'venue_booking', 'id', v_booking));
    PERFORM public.decide_safety_review(
        v_event, v_officer, 'changes_requested', 'Exit routes missing.', v_targets);
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    IF v_status <> 'Planning' THEN
        RAISE EXCEPTION 'AC4a-X1: expected Planning, got %', v_status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.safety_reviews
                   WHERE event_request_id = v_event AND decision = 'changes_requested'
                     AND reason = 'Exit routes missing.' AND targets = v_targets) THEN
        RAISE EXCEPTION 'AC4a-X1: reason or targets not kept';
    END IF;

    -- AC1-X2 and AC6-X3: refused calls write nothing.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'verify SCRUM-60 refusals', 'Safety Review')
        RETURNING id INTO v_event;
    FOR v_bad IN
        SELECT * FROM (VALUES
            ('AC1-X2 non-officer', v_other, 'approved', NULL::text, '[]'::jsonb, 'P0003'),
            ('AC6-X3 rejected', v_officer, 'rejected', 'No.', '[]'::jsonb, '22023'),
            ('AC6-X3 blank reason', v_officer, 'changes_requested', '  ', '[]'::jsonb, '22023'),
            ('AC6-X3 targets not array', v_officer, 'changes_requested', 'x', '{}'::jsonb, '22023'),
            ('AC6-X3 bad target kind', v_officer, 'changes_requested', 'x',
                '[{"arrangement": "room", "id": "11111111-1111-4111-8111-111111111111"}]'::jsonb,
                '22023'),
            -- AC6-X5: NULL inputs from a direct SQL caller are refused the same way
            -- (Heng Rui, message 2196).
            ('AC6-X5 null decision', v_officer, NULL, 'x', '[]'::jsonb, '22023'),
            ('AC6-X5 null targets', v_officer, 'approved', NULL, NULL::jsonb, '22023'),
            ('AC6-X5 target without arrangement', v_officer, 'changes_requested', 'x',
                '[{"id": "11111111-1111-4111-8111-111111111111"}]'::jsonb, '22023'),
            ('AC6-X5 target without id', v_officer, 'changes_requested', 'x',
                '[{"arrangement": "venue_booking"}]'::jsonb, '22023'),
            ('AC6-X5 null target element', v_officer, 'changes_requested', 'x',
                '[null]'::jsonb, '22023')
        ) AS t(label, officer, decision, reason, targets, errcode)
    LOOP
        BEGIN
            PERFORM public.decide_safety_review(
                v_event, v_bad.officer, v_bad.decision, v_bad.reason, v_bad.targets);
            RAISE EXCEPTION '%: accepted', v_bad.label;
        EXCEPTION WHEN OTHERS THEN
            IF SQLSTATE <> v_bad.errcode THEN
                RAISE EXCEPTION '%: expected %, got % (%)',
                    v_bad.label, v_bad.errcode, SQLSTATE, SQLERRM;
            END IF;
        END;
    END LOOP;
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    SELECT count(*) INTO v_reviews FROM public.safety_reviews WHERE event_request_id = v_event;
    IF v_status <> 'Safety Review' OR v_reviews <> 0 THEN
        RAISE EXCEPTION 'AC6-X3: refused calls changed % / % reviews', v_status, v_reviews;
    END IF;

    -- AC6-X3: an event outside Safety Review is refused.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'verify SCRUM-60 planning', 'Planning')
        RETURNING id INTO v_event;
    BEGIN
        PERFORM public.decide_safety_review(v_event, v_officer, 'approved', NULL, '[]');
        RAISE EXCEPTION 'AC6-X3: decision accepted from Planning';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    -- AC6-X4: insert-only for the service role; no browser access.
    IF has_table_privilege('service_role', 'public.safety_reviews', 'UPDATE')
       OR has_table_privilege('service_role', 'public.safety_reviews', 'DELETE')
       OR has_table_privilege('service_role', 'public.safety_reviews', 'INSERT') THEN
        RAISE EXCEPTION 'AC6-X4: service_role can write safety_reviews directly';
    END IF;
    IF has_table_privilege('anon', 'public.safety_reviews', 'SELECT')
       OR has_table_privilege('authenticated', 'public.safety_reviews', 'SELECT')
       OR has_function_privilege('anon',
            'public.decide_safety_review(uuid,uuid,text,text,jsonb)', 'EXECUTE')
       OR has_function_privilege('authenticated',
            'public.decide_safety_review(uuid,uuid,text,text,jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION 'AC6-X4: a browser role has access';
    END IF;

    RAISE NOTICE 'ALL SCRUM-60 SAFETY DECISION VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
