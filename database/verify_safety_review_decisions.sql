-- Run after 0034_safety_review_decisions.sql and 0044_safety_review_null_inputs.sql
-- (SCRUM-60 increment 2).
-- Every change is rolled back. Borrows the two oldest auth users: the first as
-- organiser and Safety Officer, the second as a user without the role.

BEGIN;

DO $$
DECLARE
    v_officer uuid;
    v_other uuid;
    v_event uuid;
    v_status text;
    v_reviews int;
    v_targets jsonb := '[{"arrangement": "venue_booking",
                          "id": "11111111-1111-4111-8111-111111111111"}]';
    v_bad record;
BEGIN
    SELECT id INTO v_officer FROM auth.users ORDER BY created_at LIMIT 1;
    SELECT id INTO v_other FROM auth.users ORDER BY created_at OFFSET 1 LIMIT 1;
    IF v_other IS NULL THEN
        RAISE EXCEPTION 'Needs at least two auth users';
    END IF;
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_officer, 'safety_officer')
        ON CONFLICT DO NOTHING;
    DELETE FROM public.staff_roles WHERE user_id = v_other AND role = 'safety_officer';

    -- AC3-X1: approval confirms, records the review and the history actor.
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'verify SCRUM-60 approve', 'Safety Review')
        RETURNING id INTO v_event;
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
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_officer, 'verify SCRUM-60 changes', 'Safety Review')
        RETURNING id INTO v_event;
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
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_event;
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
