-- Behavioural verification for SCRUM-35 post-approval event amendments.
-- Run after migrations 0018 and 0019. The transaction rolls back all test data.

BEGIN;

DO $$
DECLARE
    v_organiser uuid;
    v_coord varchar := 'verify-change-coordinator';
    v_other varchar := 'verify-other-coordinator';
    v_approve_event uuid;
    v_reject_event uuid;
    v_stale_event uuid;
    v_reassigned_event uuid;
    v_change public.event_change_requests;
    v_original_updated_at timestamptz;
BEGIN
    SELECT id INTO v_organiser FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_organiser IS NULL THEN
        RAISE EXCEPTION 'Verification requires at least one Supabase Auth user';
    END IF;

    INSERT INTO public.event_requests (
        organiser_id, status, event_name, expected_attendance, venue_requirements
    ) VALUES
        (v_organiser, 'Approved', 'VERIFY change approval', 40, 'Original venue')
    RETURNING id INTO v_approve_event;
    INSERT INTO public.event_requests (
        organiser_id, status, event_name, expected_attendance
    ) VALUES (v_organiser, 'Planning', 'VERIFY change rejection', 40)
    RETURNING id INTO v_reject_event;
    INSERT INTO public.event_requests (
        organiser_id, status, event_name, expected_attendance
    ) VALUES (v_organiser, 'Approved', 'VERIFY stale change', 40)
    RETURNING id INTO v_stale_event;
    INSERT INTO public.event_requests (
        organiser_id, status, event_name, expected_attendance
    ) VALUES (v_organiser, 'Approved', 'VERIFY reassigned change', 40)
    RETURNING id INTO v_reassigned_event;

    INSERT INTO public.event_coordinator_assignments (
        event_request_id, coordinator_id, assigned_by
    ) VALUES
        (v_approve_event, v_coord, 'verify'),
        (v_reject_event, v_coord, 'verify'),
        (v_stale_event, v_coord, 'verify'),
        (v_reassigned_event, v_coord, 'verify'),
        (v_reassigned_event, v_other, 'verify-reassignment');

    -- Keep the inserted version older than this verification transaction so
    -- an approval must visibly advance it even though PostgreSQL now() is
    -- stable within a transaction.
    UPDATE public.event_requests
    SET updated_at = now() - interval '1 minute'
    WHERE id IN (v_approve_event, v_reject_event, v_stale_event, v_reassigned_event);

    -- AC1-N2: an unchanged value cannot create an amendment.
    BEGIN
        PERFORM public.create_event_change_request(
            v_approve_event, v_organiser, 'No actual change',
            jsonb_build_object('expected_attendance', 40)
        );
        RAISE EXCEPTION 'AC1-N2: unchanged values should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    ASSERT NOT EXISTS (
        SELECT 1 FROM public.event_change_requests
        WHERE event_request_id = v_approve_event
    ), 'AC1-N2: refused request must create no row';

    -- AC1-H1 and AC5-N1: creation retains one pending request and no event mutation.
    SELECT updated_at INTO v_original_updated_at
    FROM public.event_requests WHERE id = v_approve_event;
    v_change := public.create_event_change_request(
        v_approve_event, v_organiser, 'Increase capacity and change venue',
        jsonb_build_object(
            'expected_attendance', 80,
            'venue_requirements', 'Lecture theatre'
        )
    );
    ASSERT v_change.status = 'Pending', 'AC1-H1: request should be Pending';
    ASSERT (
        SELECT expected_attendance = 40 AND venue_requirements = 'Original venue'
        FROM public.event_requests WHERE id = v_approve_event
    ), 'AC1-H1: pending request must not alter the event';
    BEGIN
        PERFORM public.create_event_change_request(
            v_approve_event, v_organiser, 'Second pending request',
            jsonb_build_object('expected_attendance', 90)
        );
        RAISE EXCEPTION 'AC5-N1: duplicate pending request should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    ASSERT (
        SELECT count(*) = 1 FROM public.event_change_requests
        WHERE event_request_id = v_approve_event
    ), 'AC5-N1: only the original pending request should remain';

    -- AC3-H1: approval applies all values and decision metadata atomically.
    v_change := public.decide_event_change_request(
        v_approve_event, v_change.id, v_coord, 'Approved', NULL
    );
    ASSERT v_change.status = 'Approved', 'AC3-H1: decision should be Approved';
    ASSERT v_change.coordinator_id = v_coord,
        'AC3-H1: assigned coordinator should be retained';
    ASSERT v_change.decided_at IS NOT NULL,
        'AC3-H1: decision timestamp should be retained';
    ASSERT (
        SELECT expected_attendance = 80
        FROM public.event_requests WHERE id = v_approve_event
    ), 'AC3-H1: attendance should be updated';
    ASSERT (
        SELECT venue_requirements = 'Lecture theatre'
        FROM public.event_requests WHERE id = v_approve_event
    ), 'AC3-H1: venue requirement should be updated';
    ASSERT (
        SELECT event_name = 'VERIFY change approval'
        FROM public.event_requests WHERE id = v_approve_event
    ), 'AC3-H1: unrelated fields should remain unchanged';
    ASSERT (
        SELECT updated_at > v_original_updated_at
        FROM public.event_requests WHERE id = v_approve_event
    ), 'AC3-H1: event version timestamp should advance';

    -- AC4-H1: rejection records the reason without changing the event.
    v_change := public.create_event_change_request(
        v_reject_event, v_organiser, 'Capacity request',
        jsonb_build_object('expected_attendance', 60)
    );
    v_change := public.decide_event_change_request(
        v_reject_event, v_change.id, v_coord, 'Rejected', 'Capacity unavailable'
    );
    ASSERT v_change.status = 'Rejected', 'AC4-H1: decision should be Rejected';
    ASSERT v_change.decision_reason = 'Capacity unavailable',
        'AC4-H1: rejection reason should be retained';
    ASSERT (
        SELECT expected_attendance = 40
        FROM public.event_requests WHERE id = v_reject_event
    ), 'AC4-H1: rejection must not alter the event';

    -- AC6-N1: changed source data makes approval stale with no partial write.
    v_change := public.create_event_change_request(
        v_stale_event, v_organiser, 'Stale capacity request',
        jsonb_build_object('expected_attendance', 70)
    );
    UPDATE public.event_requests
    SET venue_requirements = 'Changed after request',
        updated_at = clock_timestamp() + interval '1 second'
    WHERE id = v_stale_event;
    BEGIN
        PERFORM public.decide_event_change_request(
            v_stale_event, v_change.id, v_coord, 'Approved', NULL
        );
        RAISE EXCEPTION 'AC6-N1: stale approval should raise P0004';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    ASSERT (
        SELECT expected_attendance = 40
        FROM public.event_requests WHERE id = v_stale_event
    ), 'AC6-N1: stale approval must not apply proposed values';
    ASSERT (
        SELECT status = 'Pending' FROM public.event_change_requests
        WHERE id = v_change.id
    ), 'AC6-N1: stale approval must leave the request pending';

    -- AC5-N3: the former coordinator loses authority after reassignment.
    v_change := public.create_event_change_request(
        v_reassigned_event, v_organiser, 'Reassigned capacity request',
        jsonb_build_object('expected_attendance', 75)
    );
    BEGIN
        PERFORM public.decide_event_change_request(
            v_reassigned_event, v_change.id, v_coord, 'Approved', NULL
        );
        RAISE EXCEPTION 'AC5-N3: former coordinator should raise P0003';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;
    ASSERT (
        SELECT expected_attendance = 40
        FROM public.event_requests WHERE id = v_reassigned_event
    ), 'AC5-N3: forbidden decision must not alter the event';
    ASSERT (
        SELECT status = 'Pending' FROM public.event_change_requests
        WHERE id = v_change.id
    ), 'AC5-N3: forbidden decision must not alter the request';

    -- AC3-X1: browser roles cannot bypass the server workflow.
    ASSERT NOT has_table_privilege(
        'anon', 'public.event_change_requests', 'SELECT'
    ), 'AC3-X1: anon must not read change requests directly';
    ASSERT NOT has_table_privilege(
        'authenticated', 'public.event_change_requests', 'SELECT'
    ), 'AC3-X1: authenticated must not read change requests directly';
    ASSERT NOT has_function_privilege(
        'authenticated',
        'public.create_event_change_request(uuid, uuid, text, jsonb)',
        'EXECUTE'
    ), 'AC3-X1: authenticated must not create changes directly';
    ASSERT NOT has_function_privilege(
        'authenticated',
        'public.decide_event_change_request(uuid, uuid, varchar, text, text)',
        'EXECUTE'
    ), 'AC3-X1: authenticated must not decide changes directly';
    ASSERT has_function_privilege(
        'service_role',
        'public.create_event_change_request(uuid, uuid, text, jsonb)',
        'EXECUTE'
    ), 'AC3-X1: service role must create changes through the backend';
    ASSERT has_function_privilege(
        'service_role',
        'public.decide_event_change_request(uuid, uuid, varchar, text, text)',
        'EXECUTE'
    ), 'AC3-X1: service role must decide changes through the backend';

    RAISE NOTICE 'ALL EVENT CHANGE REQUEST VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
