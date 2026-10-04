-- Behavioural verification for SCRUM-17 review decisions.
-- Run after migration 0016. The transaction rolls back all verification data.

BEGIN;

DO $$
DECLARE
    v_organiser uuid;
    v_coord varchar := 'verify-review-coordinator';
    v_other varchar := 'verify-other-coordinator';
    v_approve uuid;
    v_changes uuid;
    v_reject uuid;
    v_reassigned uuid;
    v_missing uuid := '11111111-1111-1111-1111-111111111111';
    v_row public.event_requests;
    v_count integer;
BEGIN
    SELECT id INTO v_organiser FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_organiser IS NULL THEN
        RAISE EXCEPTION 'Verification requires at least one Supabase Auth user';
    END IF;

    INSERT INTO public.event_requests (organiser_id, status, event_name)
    VALUES (v_organiser, 'Under Review', 'VERIFY approve')
    RETURNING id INTO v_approve;
    INSERT INTO public.event_requests (organiser_id, status, event_name)
    VALUES (v_organiser, 'Under Review', 'VERIFY changes')
    RETURNING id INTO v_changes;
    INSERT INTO public.event_requests (organiser_id, status, event_name)
    VALUES (v_organiser, 'Under Review', 'VERIFY reject')
    RETURNING id INTO v_reject;
    INSERT INTO public.event_requests (organiser_id, status, event_name)
    VALUES (v_organiser, 'Under Review', 'VERIFY reassigned')
    RETURNING id INTO v_reassigned;

    INSERT INTO public.event_coordinator_assignments (
        event_request_id, coordinator_id, assigned_by
    ) VALUES
        (v_approve, v_coord, 'verify'),
        (v_changes, v_coord, 'verify'),
        (v_reject, v_coord, 'verify'),
        (v_reassigned, v_coord, 'verify'),
        (v_reassigned, v_other, 'verify-reassignment');

    -- 1. Unknown requests are refused without creating history.
    BEGIN
        PERFORM public.decide_event_request_by_coordinator(
            v_missing, v_coord, 'Approved', NULL
        );
        RAISE EXCEPTION 'verify 1: unknown request should raise P0002';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;

    -- 2. An unrelated coordinator cannot decide the request.
    BEGIN
        PERFORM public.decide_event_request_by_coordinator(
            v_approve, v_other, 'Approved', NULL
        );
        RAISE EXCEPTION 'verify 2: unrelated coordinator should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;

    -- A coordinator loses mutation authority immediately after reassignment.
    BEGIN
        PERFORM public.decide_event_request_by_coordinator(
            v_reassigned, v_coord, 'Approved', NULL
        );
        RAISE EXCEPTION 'verify 2: reassigned coordinator should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;
    ASSERT (
        SELECT status = 'Under Review'
        FROM public.event_requests WHERE id = v_reassigned
    ), 'verify 2: reassignment refusal must preserve status';
    ASSERT NOT EXISTS (
        SELECT 1 FROM public.event_request_review_decisions
        WHERE event_request_id = v_reassigned
    ), 'verify 2: reassignment refusal must create no decision';

    -- 3. Returned and rejected requests require a meaningful reason.
    BEGIN
        PERFORM public.decide_event_request_by_coordinator(
            v_changes, v_coord, 'Changes Requested', '   '
        );
        RAISE EXCEPTION 'verify 3: blank changes reason should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    BEGIN
        PERFORM public.decide_event_request_by_coordinator(
            v_reject, v_coord, 'Rejected', NULL
        );
        RAISE EXCEPTION 'verify 3: missing rejection reason should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    SELECT count(*) INTO v_count
    FROM public.event_request_review_decisions
    WHERE event_request_id IN (v_approve, v_changes, v_reject);
    ASSERT v_count = 0, 'verify 1-3: refused decisions must create no history';

    -- 4. Approval changes status and records an outcome in one call.
    v_row := public.decide_event_request_by_coordinator(
        v_approve, v_coord, 'Approved', 'Ready for planning'
    );
    ASSERT v_row.status = 'Approved', 'verify 4: request should be Approved';

    -- 5. A clarification request retains its reason.
    v_row := public.decide_event_request_by_coordinator(
        v_changes, v_coord, 'Changes Requested', 'Clarify equipment needs'
    );
    ASSERT v_row.status = 'Changes Requested',
        'verify 5: request should be Changes Requested';
    ASSERT EXISTS (
        SELECT 1 FROM public.event_request_review_decisions
        WHERE event_request_id = v_changes
          AND decision_status = 'Changes Requested'
          AND reason = 'Clarify equipment needs'
    ), 'verify 5: clarification reason should be retained';

    -- 6. Only the owner can answer; answering does not mutate request status.
    BEGIN
        PERFORM public.respond_to_event_request_clarification(
            v_changes, v_missing, 'should not be stored'
        );
        RAISE EXCEPTION 'verify 6: unrelated organiser should raise P0002';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;
    PERFORM public.respond_to_event_request_clarification(
        v_changes, v_organiser, 'A wireless microphone is required'
    );
    ASSERT (
        SELECT status = 'Changes Requested'
        FROM public.event_requests WHERE id = v_changes
    ), 'verify 6: organiser response must not change request status';
    ASSERT EXISTS (
        SELECT 1 FROM public.event_request_review_decisions
        WHERE event_request_id = v_changes
          AND organiser_response = 'A wireless microphone is required'
          AND responded_at IS NOT NULL
    ), 'verify 6: organiser response should be retained';

    -- 7. Only the assigned coordinator can resume after a response exists.
    BEGIN
        PERFORM public.resume_event_request_review_by_coordinator(
            v_changes, v_other
        );
        RAISE EXCEPTION 'verify 7: unrelated coordinator should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;
    v_row := public.resume_event_request_review_by_coordinator(
        v_changes, v_coord
    );
    ASSERT v_row.status = 'Under Review',
        'verify 7: responded request should return to Under Review';

    -- 8. A later approval appends history without replacing the clarification.
    v_row := public.decide_event_request_by_coordinator(
        v_changes, v_coord, 'Approved', NULL
    );
    ASSERT v_row.status = 'Approved',
        'verify 8: resumed request should be Approved';
    SELECT count(*) INTO v_count
    FROM public.event_request_review_decisions
    WHERE event_request_id = v_changes;
    ASSERT v_count = 2,
        'verify 8: clarification and approval should both remain';
    ASSERT EXISTS (
        SELECT 1 FROM public.event_request_review_decisions
        WHERE event_request_id = v_changes
          AND decision_status = 'Changes Requested'
          AND reason = 'Clarify equipment needs'
          AND organiser_response = 'A wireless microphone is required'
    ), 'verify 8: approval must not overwrite the clarification exchange';

    -- 9. Rejection changes status and retains its reason.
    v_row := public.decide_event_request_by_coordinator(
        v_reject, v_coord, 'Rejected', 'Outside programme scope'
    );
    ASSERT v_row.status = 'Rejected', 'verify 9: request should be Rejected';

    -- 10. Repeated or stale decisions cannot add a second history row.
    BEGIN
        PERFORM public.decide_event_request_by_coordinator(
            v_approve, v_coord, 'Rejected', 'stale decision'
        );
        RAISE EXCEPTION 'verify 7: repeated decision should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    SELECT count(*) INTO v_count
    FROM public.event_request_review_decisions
    WHERE event_request_id = v_approve;
    ASSERT v_count = 1, 'verify 10: stale action must not create history';

    -- 11. Direct client roles cannot read the history table or execute the RPCs.
    ASSERT NOT has_table_privilege(
        'anon', 'public.event_request_review_decisions', 'SELECT'
    ), 'verify 8: anon must not read decision history';
    ASSERT NOT has_table_privilege(
        'authenticated', 'public.event_request_review_decisions', 'SELECT'
    ), 'verify 8: authenticated must not read decision history directly';
    ASSERT NOT has_function_privilege(
        'anon',
        'public.decide_event_request_by_coordinator(uuid, varchar, varchar, text)',
        'EXECUTE'
    ), 'verify 8: anon must not execute the decision function';
    ASSERT NOT has_function_privilege(
        'authenticated',
        'public.decide_event_request_by_coordinator(uuid, varchar, varchar, text)',
        'EXECUTE'
    ), 'verify 8: authenticated must not execute the decision function';
    ASSERT has_function_privilege(
        'service_role',
        'public.decide_event_request_by_coordinator(uuid, varchar, varchar, text)',
        'EXECUTE'
    ), 'verify 8: service_role must execute the decision function';
    ASSERT NOT has_function_privilege(
        'authenticated',
        'public.respond_to_event_request_clarification(uuid, uuid, text)',
        'EXECUTE'
    ), 'verify 10: authenticated must not execute the response function';
    ASSERT NOT has_function_privilege(
        'authenticated',
        'public.resume_event_request_review_by_coordinator(uuid, varchar)',
        'EXECUTE'
    ), 'verify 10: authenticated must not execute the resume function';
    ASSERT has_function_privilege(
        'service_role',
        'public.respond_to_event_request_clarification(uuid, uuid, text)',
        'EXECUTE'
    ), 'verify 10: service_role must execute the response function';
    ASSERT has_function_privilege(
        'service_role',
        'public.resume_event_request_review_by_coordinator(uuid, varchar)',
        'EXECUTE'
    ), 'verify 10: service_role must execute the resume function';

    RAISE NOTICE 'ALL EVENT-REQUEST REVIEW DECISION VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
