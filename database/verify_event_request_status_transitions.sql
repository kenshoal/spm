-- Behavioural verification for advance_event_request_by_coordinator (SCRUM-28).
--
-- Run in the Supabase SQL Editor AFTER applying migrations 0012 and 0013. Exercises the
-- real function rather than the API layer: every allowed coordinator
-- transition, the P0002 / P0003 / P0004 errcode contract, "no mutation on a
-- refused call", reassignment handling and the EXECUTE grants. The whole
-- script runs in one transaction and ROLLBACKs, so it leaves no data behind —
-- pass/fail is the final NOTICE or the first error message.
--
-- Not covered here: the service's role checks (event_coordinator only) and
-- the HTTP 403/409/404 mapping — those live in eventRequestService's pytest
-- suite. Confirmed is written directly below as a stand-in for the venue/ops
-- stories that own that transition.

BEGIN;

DO $$
DECLARE
    v_organiser uuid;
    v_coord_a varchar := 'verify-coordinator-a';
    v_coord_b varchar := 'verify-coordinator-b';
    v_missing uuid := '11111111-1111-1111-1111-111111111111';
    v_review uuid;
    v_complete uuid;
    v_draft uuid;
    v_row public.event_requests;
    v_status text;
BEGIN
    SELECT id INTO v_organiser FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_organiser IS NULL THEN
        RAISE EXCEPTION 'Verification requires at least one Supabase Auth user';
    END IF;

    INSERT INTO public.event_requests (
        organiser_id, status, event_name, purpose, description,
        proposed_date_times, expected_attendance, venue_requirements,
        accessibility_needs, equipment_requirements, registration_needs
    )
    VALUES
        (v_organiser, 'Submitted', 'VERIFY review/cancel', 'verify', 'rollback-only',
         ARRAY['2026-10-20T02:00:00Z'::timestamptz], 20, 'None', 'None', 'None', 'None'),
        (v_organiser, 'Submitted', 'VERIFY completion', 'verify', 'rollback-only',
         ARRAY['2026-10-21T02:00:00Z'::timestamptz], 20, 'None', 'None', 'None', 'None');

    SELECT id INTO v_review FROM public.event_requests
    WHERE event_name = 'VERIFY review/cancel' AND organiser_id = v_organiser
    ORDER BY created_at DESC LIMIT 1;
    SELECT id INTO v_complete FROM public.event_requests
    WHERE event_name = 'VERIFY completion' AND organiser_id = v_organiser
    ORDER BY created_at DESC LIMIT 1;

    INSERT INTO public.event_requests (organiser_id, status, event_name)
    VALUES (v_organiser, 'Draft', 'VERIFY draft')
    RETURNING id INTO v_draft;

    -- AC3-N1 (negative, SCRUM-28): an unknown request id is refused (P0002)
    -- 1. P0002: unknown request id
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_missing, v_coord_a, 'Under Review');
        RAISE EXCEPTION 'verify 1: unknown id should raise P0002';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;

    -- AC3-N2 (negative, SCRUM-28): an unassigned request (and a Draft, which never
    -- carries one) is refused (P0003)
    -- 2. P0003: no assignment yet (also covers Drafts, which never have one)
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_review, v_coord_a, 'Under Review');
        RAISE EXCEPTION 'verify 2: unassigned request should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_draft, v_coord_a, 'Cancelled');
        RAISE EXCEPTION 'verify 2: Draft should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;

    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    VALUES (v_review, v_coord_a, 'verify'), (v_complete, v_coord_a, 'verify');

    -- AC3-N3, AC5 (negative, SCRUM-28): a coordinator who is not the latest assignee
    -- is refused (P0003)
    -- 3. P0003: a coordinator who is not the assigned one
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_review, v_coord_b, 'Under Review');
        RAISE EXCEPTION 'verify 3: unrelated coordinator should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;

    -- AC2-N4, AC3 (negative, SCRUM-28): Submitted -> Approved is not this boundary's
    -- move (P0004); approval belongs to SCRUM-17
    -- 4. P0004: a transition this function does not own (approval)
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_review, v_coord_a, 'Approved');
        RAISE EXCEPTION 'verify 4: Submitted -> Approved should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    -- AC2-N5, AC3 (negative, SCRUM-28): completion is refused before Confirmed (P0004)
    -- 5. P0004: completion before Confirmed
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_review, v_coord_a, 'Completed');
        RAISE EXCEPTION 'verify 5: Submitted -> Completed should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    SELECT status INTO v_status FROM public.event_requests WHERE id = v_review;
    ASSERT v_status = 'Submitted', 'verify 1-5: refused calls must not change the status';

    -- AC3-H1, AC2 (happy, SCRUM-28): Submitted -> Under Review succeeds under the row lock
    -- 6. Submitted -> Under Review by the assigned coordinator
    v_row := advance_event_request_by_coordinator(v_review, v_coord_a, 'Under Review');
    ASSERT v_row.status = 'Under Review', 'verify 6: returned row should be Under Review';

    -- AC3-N6, AC7 (negative, SCRUM-28): repeated review is refused (P0004)
    -- 7. Repeated review is refused and leaves the status unchanged
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_review, v_coord_a, 'Under Review');
        RAISE EXCEPTION 'verify 7: repeated review should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    -- AC3-N7, AC5 (negative, SCRUM-28): a reassigned-away coordinator is refused (P0003)
    -- 8. Reassignment: only the latest-assigned coordinator may act
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    VALUES (v_review, v_coord_b, 'verify');
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_review, v_coord_a, 'Cancelled');
        RAISE EXCEPTION 'verify 8: reassigned-away coordinator should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;

    -- AC3-P1, AC2 (partition, SCRUM-28): any non-terminal status may be cancelled
    -- 9. Non-terminal -> Cancelled by the current coordinator
    v_row := advance_event_request_by_coordinator(v_review, v_coord_b, 'Cancelled');
    ASSERT v_row.status = 'Cancelled', 'verify 9: returned row should be Cancelled';

    -- AC3-N8, AC7 (negative, SCRUM-28): Cancelled is terminal (P0004)
    -- 10. Cancelled is terminal
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_review, v_coord_b, 'Cancelled');
        RAISE EXCEPTION 'verify 10: cancelling a Cancelled request should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    -- AC3-P2, AC2 (partition, SCRUM-28): Confirmed -> Completed through the RPC
    -- 11. Confirmed -> Completed (Confirmed seeded directly; owned by other stories)
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_complete;
    v_row := advance_event_request_by_coordinator(v_complete, v_coord_a, 'Completed');
    ASSERT v_row.status = 'Completed', 'verify 11: returned row should be Completed';

    -- AC3-N9, AC7 (negative, SCRUM-28): Completed is terminal for both actions (P0004)
    -- 12. Completed is terminal for both cancel and complete
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_complete, v_coord_a, 'Cancelled');
        RAISE EXCEPTION 'verify 12: cancelling a Completed request should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    BEGIN
        PERFORM advance_event_request_by_coordinator(v_complete, v_coord_a, 'Completed');
        RAISE EXCEPTION 'verify 12: completing twice should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;

    -- AC3-X1 (cross-cutting, SCRUM-28): only the server role executes the transition RPC
    -- 13. EXECUTE is server-only (0006 pattern)
    ASSERT NOT has_function_privilege('anon',
        'advance_event_request_by_coordinator(uuid, varchar, varchar)', 'EXECUTE'),
        'verify 13: anon must not execute the function';
    ASSERT NOT has_function_privilege('authenticated',
        'advance_event_request_by_coordinator(uuid, varchar, varchar)', 'EXECUTE'),
        'verify 13: authenticated must not execute the function';
    ASSERT has_function_privilege('service_role',
        'advance_event_request_by_coordinator(uuid, varchar, varchar)', 'EXECUTE'),
        'verify 13: service_role must execute the function';

    RAISE NOTICE 'ALL EVENT-REQUEST STATUS TRANSITION VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
