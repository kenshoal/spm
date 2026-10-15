-- SCRUM-58: real Postgres evidence for Approved -> Planning; every fixture rolls back.
-- Run after 0026. Requires an existing auth user. Prints ALL EVENT PLANNING VERIFICATIONS PASSED.
BEGIN;
DO $$
DECLARE
    v_owner uuid;
    v_event uuid;
    v_snapshot jsonb;
    v_history_count bigint;
    v_history public.event_request_status_history;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
    VALUES (v_owner, 'VERIFY SCRUM-58 planning', 'Draft') RETURNING id INTO v_event;
    -- No story writes Approved without a review yet, so the fixture sets it directly.
    UPDATE public.event_requests SET status = 'Approved' WHERE id = v_event;
    INSERT INTO public.event_coordinator_assignments(event_request_id, coordinator_id, assigned_by)
    VALUES (v_event, 'scrum58-coordinator', 'scrum58-manager');
    SELECT to_jsonb(e) INTO v_snapshot FROM public.event_requests e WHERE id = v_event;
    SELECT count(*) INTO v_history_count FROM public.event_request_status_history WHERE event_request_id = v_event;

    -- AC4-N7 (negative): another coordinator is refused with P0003, no status or history change.
    BEGIN
        PERFORM public.advance_event_request_by_coordinator(v_event, 'other-coordinator', 'Planning');
        RAISE EXCEPTION 'AC4-N7: unassigned coordinator started planning';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    ASSERT (SELECT to_jsonb(e) = v_snapshot FROM public.event_requests e WHERE id = v_event),
        'AC4-N7: refused call changed the event';
    ASSERT (SELECT count(*) = v_history_count FROM public.event_request_status_history WHERE event_request_id = v_event),
        'AC4-N7: refused call wrote history';

    -- AC1-X1 (cross-cutting): the assigned coordinator moves Approved -> Planning, one history row names them.
    PERFORM public.advance_event_request_by_coordinator(v_event, 'scrum58-coordinator', 'Planning');
    ASSERT (SELECT status = 'Planning' FROM public.event_requests WHERE id = v_event),
        'AC1-X1: status is not Planning';
    ASSERT (SELECT count(*) = v_history_count + 1 FROM public.event_request_status_history WHERE event_request_id = v_event),
        'AC1-X1: expected exactly one new history row';
    SELECT * INTO v_history FROM public.event_request_status_history
    WHERE event_request_id = v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_history.previous_status = 'Approved' AND v_history.new_status = 'Planning'
        AND v_history.entry_kind = 'transition', 'AC1-X1: wrong transition recorded';
    ASSERT v_history.actor_id = 'scrum58-coordinator' AND v_history.actor_role = 'event_coordinator'
        AND v_history.source = 'coordinator.planning', 'AC1-X1: wrong actor or source recorded';

    -- AC4-N8 (negative): browser roles cannot call the function; the server role still can.
    ASSERT NOT has_function_privilege('anon',
        'public.advance_event_request_by_coordinator(uuid, varchar, varchar)', 'EXECUTE'), 'AC4-N8: anon can execute';
    ASSERT NOT has_function_privilege('authenticated',
        'public.advance_event_request_by_coordinator(uuid, varchar, varchar)', 'EXECUTE'), 'AC4-N8: authenticated can execute';
    ASSERT has_function_privilege('service_role',
        'public.advance_event_request_by_coordinator(uuid, varchar, varchar)', 'EXECUTE'), 'AC4-N8: service_role lost execute';

    RAISE NOTICE 'ALL EVENT PLANNING VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
