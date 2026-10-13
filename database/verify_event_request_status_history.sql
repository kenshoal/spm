-- SCRUM-48: real Postgres transaction evidence; every fixture rolls back.
BEGIN;
DO $$
DECLARE
    v_owner uuid;
    v_event uuid;
    v_other uuid;
    v_initial uuid;
    v_snapshot jsonb;
    v_count bigint;
    v_history public.event_request_status_history;
    v_bad text;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
    VALUES (v_owner, 'VERIFY SCRUM-48 history', 'Draft') RETURNING id INTO v_event;

    -- AC1-P1 (partition): creation must retain its initial status atomically.
    IF to_regclass('public.event_request_status_history') IS NULL THEN
        RAISE EXCEPTION 'AC1-P1: creation did not record status history';
    END IF;
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id = v_event;
    ASSERT v_history.new_status = 'Draft' AND v_history.previous_status IS NULL;
    ASSERT v_history.actor_id = v_owner::text AND v_history.actor_role = 'event_organiser';
    ASSERT v_history.entry_kind = 'created' AND v_history.occurred_at IS NOT NULL;
    ASSERT (SELECT count(*) = 1 FROM public.event_request_status_history WHERE event_request_id = v_event);

    UPDATE public.event_requests SET status = 'Submitted' WHERE id = v_event;
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id = v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_history.previous_status = 'Draft' AND v_history.new_status = 'Submitted';
    ASSERT v_history.actor_id = v_owner::text AND v_history.source = 'event_request.submitted';
    INSERT INTO public.event_coordinator_assignments(event_request_id, coordinator_id, assigned_by)
    VALUES(v_event, 'scrum48-coordinator', 'scrum48-manager');

    -- AC1-H1 (happy): the locked coordinator transition records one matching entry.
    PERFORM public.advance_event_request_by_coordinator(v_event, 'scrum48-coordinator', 'Under Review');
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id = v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_history.previous_status = 'Submitted' AND v_history.new_status = 'Under Review';
    ASSERT v_history.actor_id = 'scrum48-coordinator' AND v_history.actor_role = 'event_coordinator';
    ASSERT v_history.source = 'coordinator.review';
    ASSERT (SELECT count(*) = 3 FROM public.event_request_status_history WHERE event_request_id = v_event);
    SELECT to_jsonb(e) INTO v_snapshot FROM public.event_requests e WHERE id = v_event;

    -- AC3-N1, AC3-N2 (negative): repeated and forbidden transitions add nothing.
    BEGIN
        PERFORM public.advance_event_request_by_coordinator(v_event, 'scrum48-coordinator', 'Under Review');
        RAISE EXCEPTION 'Repeated transition succeeded unexpectedly';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    BEGIN
        PERFORM public.advance_event_request_by_coordinator(v_event, 'other-coordinator', 'Cancelled');
        RAISE EXCEPTION 'Unrelated coordinator succeeded unexpectedly';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    ASSERT (SELECT to_jsonb(e) = v_snapshot FROM public.event_requests e WHERE id = v_event);
    ASSERT (SELECT count(*) = 3 FROM public.event_request_status_history WHERE event_request_id = v_event);
    ASSERT NOT EXISTS(SELECT 1 FROM public.event_request_review_decisions WHERE event_request_id=v_event);
    ASSERT (SELECT count(*)=1 FROM public.event_request_outbox WHERE event_request_id=v_event);
    ASSERT (SELECT count(*)=1 FROM public.event_coordinator_assignments WHERE event_request_id=v_event);

    -- AC3-N3 (negative): edits and same-status writes are not transitions.
    UPDATE public.event_requests SET event_name = 'VERIFY SCRUM-48 edited', status = status WHERE id = v_event;
    ASSERT (SELECT count(*) = 3 FROM public.event_request_status_history WHERE event_request_id = v_event);

    -- AC2-H1 (happy): clarification response is not a transition; resume is.
    PERFORM public.decide_event_request_by_coordinator(v_event, 'scrum48-coordinator', 'Changes Requested', 'Clarify attendance');
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id=v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_history.previous_status='Under Review' AND v_history.new_status='Changes Requested';
    ASSERT v_history.actor_id='scrum48-coordinator' AND v_history.source='coordinator.decision';
    PERFORM public.respond_to_event_request_clarification(v_event, v_owner, 'Attendance confirmed');
    ASSERT (SELECT count(*) = 4 FROM public.event_request_status_history WHERE event_request_id = v_event);
    PERFORM public.resume_event_request_review_by_coordinator(v_event, 'scrum48-coordinator');
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id = v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_history.previous_status = 'Changes Requested' AND v_history.new_status = 'Under Review';
    ASSERT v_history.actor_id = 'scrum48-coordinator' AND v_history.source = 'coordinator.resume_review';
    PERFORM public.decide_event_request_by_coordinator(v_event, 'scrum48-coordinator', 'Approved');
    SELECT to_jsonb(e) INTO v_snapshot FROM public.event_requests e WHERE id = v_event;

    -- AC1-N1 (negative): failure inside history insertion rolls the event write back.
    BEGIN
        PERFORM pg_catalog.set_config('app.event_status_actor', jsonb_build_object(
            'event_request_id', v_event, 'actor_id', 'test', 'source', 'test.injected_failure'
        )::text, true); -- Missing role intentionally violates the history NOT NULL constraint.
        UPDATE public.event_requests SET status = 'Planning' WHERE id = v_event;
        RAISE EXCEPTION 'History insertion should have failed';
    EXCEPTION WHEN not_null_violation THEN NULL; END;
    ASSERT (SELECT to_jsonb(e) = v_snapshot FROM public.event_requests e WHERE id = v_event);
    ASSERT (SELECT count(*) = 6 FROM public.event_request_status_history WHERE event_request_id = v_event);

    -- AC2-P1 (partition): a named system action uses the same atomic trigger.
    PERFORM private.set_event_status_actor(v_event, NULL, 'system', 'test.system_transition');
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_event;
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id = v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_history.actor_id IS NULL AND v_history.actor_role = 'system' AND v_history.source = 'test.system_transition';
    ASSERT v_history.new_status = (SELECT status FROM public.event_requests WHERE id = v_event);
    ASSERT NOT EXISTS (
        SELECT 1 FROM (SELECT occurred_at, lag(occurred_at) OVER (ORDER BY id) AS previous_time
            FROM public.event_request_status_history WHERE event_request_id = v_event) h
        WHERE occurred_at <= previous_time
    );

    -- AC5-N2 (negative): retained evidence cannot be independently edited, deleted or truncated.
    BEGIN
        UPDATE public.event_request_status_history SET source = 'tampered' WHERE event_request_id = v_event;
        RAISE EXCEPTION 'History edit should have failed';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    BEGIN
        DELETE FROM public.event_request_status_history WHERE event_request_id = v_event;
        RAISE EXCEPTION 'History deletion should have failed';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    BEGIN
        TRUNCATE public.event_request_status_history;
        RAISE EXCEPTION 'History truncation should have failed';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    ASSERT (SELECT count(*) = 7 FROM public.event_request_status_history WHERE event_request_id = v_event);
    ASSERT NOT has_table_privilege('anon', 'public.event_request_status_history', 'SELECT');
    ASSERT NOT has_table_privilege('authenticated', 'public.event_request_status_history', 'SELECT');
    ASSERT NOT has_table_privilege('service_role', 'public.event_request_status_history', 'INSERT');
    ASSERT NOT has_table_privilege('service_role', 'public.event_request_status_history', 'UPDATE');
    ASSERT NOT has_table_privilege('service_role', 'public.event_request_status_history', 'DELETE');
    ASSERT NOT has_table_privilege('service_role', 'public.event_request_status_history', 'TRUNCATE');
    ASSERT (SELECT relrowsecurity FROM pg_class WHERE oid='public.event_request_status_history'::regclass);
    ASSERT NOT has_function_privilege('anon', 'private.set_event_status_actor(uuid,text,text,text)', 'EXECUTE');
    ASSERT NOT has_function_privilege('authenticated', 'private.set_event_status_actor(uuid,text,text,text)', 'EXECUTE');

    -- AC5-N3 (negative): discard still removes an unsubmitted Draft and its evidence.
    INSERT INTO public.event_requests(organiser_id, status) VALUES(v_owner, 'Draft') RETURNING id INTO v_other;
    DELETE FROM public.event_requests WHERE id = v_other;
    ASSERT NOT EXISTS(SELECT 1 FROM public.event_request_status_history WHERE event_request_id = v_other);

    -- AC1-P2 (partition): direct submission does not invent a separate Draft phase.
    INSERT INTO public.event_requests(organiser_id, status) VALUES(v_owner, 'Submitted') RETURNING id INTO v_other;
    ASSERT (SELECT count(*) = 1 FROM public.event_request_status_history WHERE event_request_id = v_other);
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id = v_other;
    ASSERT v_history.previous_status IS NULL AND v_history.new_status = 'Submitted';

    -- AC1-N2 (negative): an aborted creation has neither a request nor history afterwards.
    SELECT count(*) INTO v_count FROM public.event_request_status_history;
    BEGIN
        INSERT INTO public.event_requests(organiser_id,status) VALUES(v_owner,'Draft') RETURNING id INTO v_initial;
        RAISE EXCEPTION 'Test rollback' USING ERRCODE = 'P9911';
    EXCEPTION WHEN SQLSTATE 'P9911' THEN NULL; END;
    ASSERT NOT EXISTS(SELECT 1 FROM public.event_requests WHERE id = v_initial);
    ASSERT NOT EXISTS(SELECT 1 FROM public.event_request_status_history WHERE event_request_id = v_initial);
    ASSERT (SELECT count(*) FROM public.event_request_status_history) = v_count;

    -- AC2-P2 (partition): completion, cancellation and rejection retain the actual coordinator.
    FOREACH v_bad IN ARRAY ARRAY['Completed', 'Cancelled', 'Rejected'] LOOP
        INSERT INTO public.event_requests(organiser_id,status)
        VALUES(v_owner, CASE v_bad WHEN 'Completed' THEN 'Confirmed' WHEN 'Rejected' THEN 'Under Review' ELSE 'Approved' END)
        RETURNING id INTO v_other;
        INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
        VALUES(v_other,'scrum48-coordinator','scrum48-manager');
        IF v_bad = 'Rejected' THEN
            PERFORM public.decide_event_request_by_coordinator(v_other,'scrum48-coordinator',v_bad,'Not suitable');
        ELSE
            PERFORM public.advance_event_request_by_coordinator(v_other,'scrum48-coordinator',v_bad);
        END IF;
        SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id=v_other ORDER BY id DESC LIMIT 1;
        ASSERT v_history.new_status=v_bad AND v_history.actor_id='scrum48-coordinator';
        ASSERT v_history.actor_role='event_coordinator';
        ASSERT (SELECT count(*)=2 FROM public.event_request_status_history WHERE event_request_id=v_other);
    END LOOP;

    -- AC2-B1 (boundary): invalid context values fail explicitly before any write.
    FOREACH v_bad IN ARRAY ARRAY['', ' ', repeat('s',101)] LOOP
        BEGIN
            PERFORM private.set_event_status_actor(v_event,NULL,'system',v_bad);
            RAISE EXCEPTION 'Invalid source should fail';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    END LOOP;
    BEGIN
        PERFORM private.set_event_status_actor(v_event,repeat('a',65),'event_coordinator','test.boundary');
        RAISE EXCEPTION 'Oversize actor should fail';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    BEGIN
        PERFORM private.set_event_status_actor(v_event,'actor',repeat('r',65),'test.boundary');
        RAISE EXCEPTION 'Oversize role should fail';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    BEGIN
        PERFORM private.set_event_status_actor(v_event,'actor','','test.boundary');
        RAISE EXCEPTION 'Blank role should fail';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    BEGIN
        PERFORM private.set_event_status_actor(v_event,NULL,'event_coordinator','test.boundary');
        RAISE EXCEPTION 'Missing actor should fail';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
    PERFORM private.set_event_status_actor(v_event,repeat('a',63),repeat('r',63),repeat('s',99));
    UPDATE public.event_requests SET status='Approved' WHERE id=v_event;
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id=v_event ORDER BY id DESC LIMIT 1;
    ASSERT length(v_history.actor_id)=63 AND length(v_history.actor_role)=63 AND length(v_history.source)=99;
    PERFORM private.set_event_status_actor(v_event,repeat('a',64),repeat('r',64),repeat('s',100));
    UPDATE public.event_requests SET status='Confirmed' WHERE id=v_event;
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id=v_event ORDER BY id DESC LIMIT 1;
    ASSERT length(v_history.actor_id)=64 AND length(v_history.actor_role)=64 AND length(v_history.source)=100;

    -- AC2-X1 (cross-cutting): context for another event cannot leak actor attribution.
    PERFORM private.set_event_status_actor(v_other,'wrong-event-actor','event_coordinator','test.wrong_event');
    UPDATE public.event_requests SET status='Completed' WHERE id=v_event;
    SELECT * INTO v_history FROM public.event_request_status_history WHERE event_request_id=v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_history.actor_id IS NULL AND v_history.source='database.status_update';
    ASSERT nullif(current_setting('app.event_status_actor',true),'') IS NULL;

    -- AC5-N6 (negative): deleting a retained event cannot cascade away its evidence.
    INSERT INTO public.event_requests(organiser_id,status) VALUES(v_owner,'Submitted') RETURNING id INTO v_other;
    BEGIN
        DELETE FROM public.event_requests WHERE id=v_other;
        RAISE EXCEPTION 'Retained event deletion should fail';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    ASSERT EXISTS(SELECT 1 FROM public.event_requests WHERE id=v_other);
    ASSERT (SELECT count(*)=1 FROM public.event_request_status_history WHERE event_request_id=v_other);

    -- AC4-X1 (cross-cutting): migration baselines identify missing earlier evidence honestly.
    ASSERT NOT EXISTS(SELECT 1 FROM public.event_request_status_history WHERE entry_kind='baseline'
        AND (actor_id IS NOT NULL OR actor_role<>'system' OR previous_status IS NOT NULL OR source<>'history.recording_started'));

    -- AC5-X1 (cross-cutting): actual server-role RPC execution still records through protected triggers.
    INSERT INTO public.event_requests(organiser_id,status) VALUES(v_owner,'Submitted') RETURNING id INTO v_other;
    INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
    VALUES(v_other,'scrum48-coordinator','scrum48-manager');
    SET LOCAL ROLE service_role;
    PERFORM public.advance_event_request_by_coordinator(v_other,'scrum48-coordinator','Under Review');
    ASSERT (SELECT count(*)=2 FROM public.event_request_status_history WHERE event_request_id=v_other);
    RESET ROLE;

    RAISE NOTICE 'ALL EVENT STATUS HISTORY VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
