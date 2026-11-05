-- Rollback-only verification for atomic coordinator assignment.
-- Run after migration 0014. The final NOTICE indicates every assertion passed.
BEGIN;

DO $$
DECLARE
    v_organiser uuid;
    v_coordinator uuid := '88888888-8888-4888-8888-888888888888';
    v_non_coordinator uuid := '99999999-9999-4999-8999-999999999999';
    v_submitted uuid;
    v_draft uuid;
    v_terminal uuid;
    v_missing uuid := '77777777-7777-4777-8777-777777777777';
    v_assignment public.event_coordinator_assignments;
    v_count integer;
    v_definition text;
BEGIN
    SELECT id INTO v_organiser FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_organiser IS NULL THEN
        RAISE EXCEPTION 'Verification requires at least one Supabase Auth user';
    END IF;

    INSERT INTO public.staff_roles (user_id, role)
    VALUES (v_coordinator, 'event_coordinator')
    ON CONFLICT (user_id, role) DO NOTHING;

    INSERT INTO public.event_requests (organiser_id, status, event_name)
    VALUES
        (v_organiser, 'Submitted', 'VERIFY atomic assignment'),
        (v_organiser, 'Draft', 'VERIFY draft assignment'),
        (v_organiser, 'Completed', 'VERIFY terminal assignment');

    SELECT id INTO v_submitted FROM public.event_requests
    WHERE event_name = 'VERIFY atomic assignment'
    ORDER BY created_at DESC LIMIT 1;
    SELECT id INTO v_draft FROM public.event_requests
    WHERE event_name = 'VERIFY draft assignment'
    ORDER BY created_at DESC LIMIT 1;
    SELECT id INTO v_terminal FROM public.event_requests
    WHERE event_name = 'VERIFY terminal assignment'
    ORDER BY created_at DESC LIMIT 1;

    -- AC4-N3 (negative, SCRUM-28): a missing request is refused (P0002) and inserts nothing
    -- 1. Missing requests are distinguished from invalid states.
    BEGIN
        PERFORM public.assign_event_request_coordinator(
            v_missing, v_coordinator::text, v_organiser::text, NULL
        );
        RAISE EXCEPTION 'verify 1: missing request should raise P0002';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;

    -- AC4-N4 (negative, SCRUM-28): Draft and terminal requests cannot acquire an
    -- assignment (P0004)
    -- 2. Draft and terminal requests cannot acquire assignments.
    BEGIN
        PERFORM public.assign_event_request_coordinator(
            v_draft, v_coordinator::text, v_organiser::text, NULL
        );
        RAISE EXCEPTION 'verify 2: Draft should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    BEGIN
        PERFORM public.assign_event_request_coordinator(
            v_terminal, v_coordinator::text, v_organiser::text, NULL
        );
        RAISE EXCEPTION 'verify 2: Completed should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    -- AC4-N5, AC5 (negative, SCRUM-28): an identity without the coordinator role is
    -- refused (P0005) without creating an assignment
    -- 3. An arbitrary authenticated user ID cannot be assigned as coordinator.
    BEGIN
        PERFORM public.assign_event_request_coordinator(
            v_submitted, v_non_coordinator::text, v_organiser::text, NULL
        );
        RAISE EXCEPTION 'verify 3: non-coordinator should raise P0005';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN NULL;
    END;

    SELECT count(*) INTO v_count
    FROM public.event_coordinator_assignments
    WHERE event_request_id IN (v_submitted, v_draft, v_terminal);
    ASSERT v_count = 0, 'verify 1-3: refused calls must not insert assignments';

    -- AC4-H2 (happy, SCRUM-28): assignment and reassignment run through the locked RPC
    -- and preserve history
    -- 4. A valid coordinator can be assigned and then reassigned without history loss.
    -- (Hotfix 2, 0085: every call states the Coordinator the caller saw, null when there was none.)
    v_assignment := public.assign_event_request_coordinator(
        v_submitted, v_coordinator::text, v_organiser::text, NULL
    );
    ASSERT v_assignment.coordinator_id = v_coordinator::text,
        'verify 4: returned assignment should identify the coordinator';

    v_assignment := public.assign_event_request_coordinator(
        v_submitted, v_coordinator::text, v_organiser::text, v_coordinator::text
    );
    SELECT count(*) INTO v_count
    FROM public.event_coordinator_assignments
    WHERE event_request_id = v_submitted;
    ASSERT v_count = 2, 'verify 4: reassignment must preserve assignment history';

    -- AC4-H1 (happy, SCRUM-28): the assignment function locks the same event_requests
    -- row (FOR UPDATE) that transitions take
    -- 5. Assignment and status transitions must lock the same request row.
    SELECT pg_get_functiondef(
        'public.assign_event_request_coordinator(uuid, varchar, varchar, varchar)'::regprocedure
    ) INTO v_definition;
    ASSERT position('FOR UPDATE' IN upper(v_definition)) > 0,
        'verify 5: assignment function must retain the event-request row lock';

    -- AC4-X2 (cross-cutting, SCRUM-28): the assignment RPC is executable only by the
    -- backend service role
    -- 6. The RPC is callable only by the backend service role.
    ASSERT NOT has_function_privilege(
        'anon',
        'public.assign_event_request_coordinator(uuid, varchar, varchar, varchar)',
        'EXECUTE'
    ), 'verify 6: anon must not execute the function';
    ASSERT NOT has_function_privilege(
        'authenticated',
        'public.assign_event_request_coordinator(uuid, varchar, varchar, varchar)',
        'EXECUTE'
    ), 'verify 6: authenticated must not execute the function';
    ASSERT has_function_privilege(
        'service_role',
        'public.assign_event_request_coordinator(uuid, varchar, varchar, varchar)',
        'EXECUTE'
    ), 'verify 6: service_role must execute the function';

    RAISE NOTICE 'ALL ATOMIC COORDINATOR ASSIGNMENT VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;

