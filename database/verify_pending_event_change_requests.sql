-- SCRUM-35 current increment: retain Pending proposals without applying them.
-- Run after the change-request migrations; every fixture is rolled back.
BEGIN;

DO $$
DECLARE
    v_owner uuid;
    v_event uuid;
    v_change public.event_change_requests;
    v_before jsonb;
    v_outbox_count bigint;
    v_notification_count bigint;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN
        RAISE EXCEPTION 'Verification requires at least one auth user';
    END IF;
    INSERT INTO public.event_requests
        (organiser_id, status, event_name, expected_attendance, venue_requirements)
    VALUES (v_owner, 'Approved', 'VERIFY Pending-only change', 40, 'Original venue')
    RETURNING id INTO v_event;

    SELECT to_jsonb(e) INTO v_before FROM public.event_requests e WHERE id = v_event;
    SELECT count(*) INTO v_outbox_count FROM public.event_request_outbox WHERE event_request_id = v_event;
    SELECT count(*) INTO v_notification_count FROM public.notifications WHERE payload->>'event_request_id' = v_event::text;

    -- AC1-H1: proposal persistence must not overwrite any event field.
    v_change := public.create_event_change_request(
        v_event, v_owner, 'Increase capacity and update venue requirements',
        jsonb_build_object('expected_attendance', 80, 'venue_requirements', 'Lecture theatre')
    );
    ASSERT v_change.status = 'Pending';
    ASSERT v_change.coordinator_id IS NULL AND v_change.decided_at IS NULL;
    ASSERT v_change.proposed_changes = jsonb_build_object(
        'expected_attendance', 80, 'venue_requirements', 'Lecture theatre'
    );
    ASSERT (SELECT to_jsonb(e) = v_before FROM public.event_requests e WHERE id = v_event),
        'Pending creation changed the event plan';
    ASSERT (SELECT count(*) FROM public.event_request_outbox WHERE event_request_id = v_event) = v_outbox_count,
        'Pending creation emitted an outbox event';
    ASSERT (SELECT count(*) FROM public.notifications WHERE payload->>'event_request_id' = v_event::text) = v_notification_count,
        'Pending creation stored a notification';

    -- AC5-N1: a duplicate must retain the one original Pending proposal.
    BEGIN
        PERFORM public.create_event_change_request(
            v_event, v_owner, 'Another proposal', jsonb_build_object('expected_attendance', 90)
        );
        RAISE EXCEPTION 'Duplicate creation should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    ASSERT (SELECT count(*) = 1 FROM public.event_change_requests WHERE event_request_id = v_event);
    ASSERT (SELECT to_jsonb(e) = v_before FROM public.event_requests e WHERE id = v_event);

    -- AC3-X1: the browser cannot bypass API ownership or deferred decisions.
    ASSERT NOT has_table_privilege('authenticated', 'public.event_change_requests', 'SELECT');
    ASSERT NOT has_table_privilege('anon', 'public.event_change_requests', 'INSERT');
    ASSERT NOT has_function_privilege('authenticated',
        'public.decide_event_change_request(uuid,uuid,character varying,text,text)', 'EXECUTE');
    ASSERT NOT has_function_privilege('anon',
        'public.create_event_change_request(uuid,uuid,text,jsonb)', 'EXECUTE');
    ASSERT NOT has_function_privilege('authenticated',
        'public.create_event_change_request(uuid,uuid,text,jsonb)', 'EXECUTE');
    ASSERT NOT has_function_privilege('anon',
        'public.decide_event_change_request(uuid,uuid,character varying,text,text)', 'EXECUTE');

    RAISE NOTICE 'ALL PENDING EVENT CHANGE REQUEST VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
