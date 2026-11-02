-- Hotfix 2 (migrations 0085 onwards): rolled-back checks, one block per item.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_release_1_hotfixes_2.sql
-- Needs migrations 0001 to 0085 and at least two auth users. Borrows the oldest users
-- as organiser and coordinators, and adds their staff_roles rows inside the transaction.

BEGIN;

-- 0085 (H7, SCRUM-62 AC6 and SCRUM-14 AC7): reassignment from a stale view is refused
DO $$
DECLARE
    v_a uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_b uuid := (SELECT id FROM auth.users ORDER BY created_at, id OFFSET 1 LIMIT 1);
    v_event uuid;
    v_row public.event_coordinator_assignments;
BEGIN
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_a, 'event_coordinator'), (v_b, 'event_coordinator')
        ON CONFLICT DO NOTHING;
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance)
        VALUES (v_a, 'VERIFY HOTFIX 2 assignment', 'Submitted', 20) RETURNING id INTO v_event;

    ASSERT NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'assign_event_request_coordinator'
                       AND pronargs = 3),
        'H7: the three-argument function must be gone so the check cannot be skipped';

    -- AC6-H1 (happy): a first assignment from a view that showed nobody is saved
    v_row := public.assign_event_request_coordinator(v_event, v_a::text, v_b::text, NULL);
    ASSERT v_row.coordinator_id = v_a::text, 'AC6-H1: the first assignment should be saved';
    -- AC6-N2 (negative): a second assignment that still shows nobody is stale
    BEGIN
        PERFORM public.assign_event_request_coordinator(v_event, v_b::text, v_b::text, NULL);
        RAISE EXCEPTION 'AC6-N2: a stale first assignment was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0006' THEN NULL; END;
    -- AC6-N1 (negative): a reassignment naming the wrong current Coordinator is stale
    BEGIN
        PERFORM public.assign_event_request_coordinator(v_event, v_b::text, v_b::text, v_b::text);
        RAISE EXCEPTION 'AC6-N1: a stale reassignment was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0006' THEN NULL; END;
    ASSERT (SELECT count(*) FROM public.event_coordinator_assignments WHERE event_request_id = v_event) = 1,
        'AC6-N1/N2: a refused assignment must leave no row';
    -- AC6-H2 (happy): a reassignment naming the current Coordinator is saved
    v_row := public.assign_event_request_coordinator(v_event, v_b::text, v_a::text, v_a::text);
    ASSERT v_row.coordinator_id = v_b::text, 'AC6-H2: the reassignment should be saved';
    -- AC7-N1 (negative): a Withdrawn request refuses assignment
    UPDATE public.event_requests SET status = 'Withdrawn' WHERE id = v_event;
    BEGIN
        PERFORM public.assign_event_request_coordinator(v_event, v_a::text, v_a::text, v_b::text);
        RAISE EXCEPTION 'AC7-N1: a withdrawn request was assigned' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    -- AC3-P1 (partition): a Postponed request can still be reassigned
    UPDATE public.event_requests SET status = 'Postponed' WHERE id = v_event;
    v_row := public.assign_event_request_coordinator(v_event, v_a::text, v_a::text, v_b::text);
    ASSERT v_row.coordinator_id = v_a::text, 'AC3-P1: a postponed request should be reassignable';
END $$;

DO $$ BEGIN RAISE NOTICE 'ALL HOTFIX 2 VERIFICATIONS PASSED'; END $$;

ROLLBACK;
