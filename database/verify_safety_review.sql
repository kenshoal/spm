-- Run after 0029_safety_review_status.sql (SCRUM-60 increment 1).
-- Every change is rolled back. Borrows the oldest auth user as the organiser.

BEGIN;

DO $$
DECLARE
    v_owner uuid;
    v_event uuid;
    v_status text;
    v_coordinator varchar := 'verify-scrum60-coordinator';
    v_from text;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN
        RAISE EXCEPTION 'Needs at least one auth user';
    END IF;

    -- AC1-X1: the role is accepted, and an unknown role is still refused.
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_owner, 'safety_officer')
        ON CONFLICT DO NOTHING;
    BEGIN
        INSERT INTO public.staff_roles (user_id, role) VALUES (v_owner, 'verify_unknown_role');
        RAISE EXCEPTION 'AC1-X1: an unknown role was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    -- AC6-N1: the coordinator function cannot confirm from Safety Review or Planning.
    FOREACH v_from IN ARRAY ARRAY['Safety Review', 'Planning'] LOOP
        INSERT INTO public.event_requests (organiser_id, event_name, status)
            VALUES (v_owner, 'verify SCRUM-60 ' || v_from, v_from)
            RETURNING id INTO v_event;
        INSERT INTO public.event_coordinator_assignments
            (event_request_id, coordinator_id, assigned_by)
            VALUES (v_event, v_coordinator, 'verify-scrum60-lead');
        BEGIN
            PERFORM public.advance_event_request_by_coordinator(
                v_event, v_coordinator, 'Confirmed');
            RAISE EXCEPTION 'AC6-N1: coordinator confirmed from %', v_from;
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
        END;
        SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
        IF v_status <> v_from THEN
            RAISE EXCEPTION 'AC6-N1: status changed to %', v_status;
        END IF;
        IF EXISTS (SELECT 1 FROM public.event_request_status_history
                   WHERE event_request_id = v_event AND entry_kind = 'transition') THEN
            RAISE EXCEPTION 'AC6-N1: refused call wrote history';
        END IF;
    END LOOP;

    -- AC6-X1: the coordinator cancels from Safety Review, and history names them.
    SELECT id INTO v_event FROM public.event_requests
        WHERE organiser_id = v_owner AND event_name = 'verify SCRUM-60 Safety Review';
    PERFORM public.advance_event_request_by_coordinator(v_event, v_coordinator, 'Cancelled');
    SELECT status INTO v_status FROM public.event_requests WHERE id = v_event;
    IF v_status <> 'Cancelled' THEN
        RAISE EXCEPTION 'AC6-X1: expected Cancelled, got %', v_status;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.event_request_status_history
        WHERE event_request_id = v_event AND previous_status = 'Safety Review'
          AND new_status = 'Cancelled' AND actor_id = v_coordinator
          AND actor_role = 'event_coordinator' AND source = 'coordinator.cancellation'
    ) THEN
        RAISE EXCEPTION 'AC6-X1: cancellation history row missing';
    END IF;

    -- AC6-X2: browser roles still cannot call the replaced function.
    IF has_function_privilege('anon',
            'public.advance_event_request_by_coordinator(uuid,varchar,varchar)', 'EXECUTE')
        OR has_function_privilege('authenticated',
            'public.advance_event_request_by_coordinator(uuid,varchar,varchar)', 'EXECUTE') THEN
        RAISE EXCEPTION 'AC6-X2: a browser role can execute the coordinator function';
    END IF;

    RAISE NOTICE 'ALL SCRUM-60 SAFETY REVIEW VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
