-- SCRUM-22: real Postgres evidence for withdrawing a registration; every fixture rolls back.
-- Run after 0048 and 0062. Prints ALL REGISTRATION WITHDRAWAL VERIFICATIONS PASSED.
-- The races (AC3-X1, AC3-X2) need two sessions: verify_registration_withdrawal_race.sh.
-- Not covered here (their migrations are not in dev yet): AC1-H3 (SCRUM-41, 0060),
-- AC2-N8 / AC2-N9 (SCRUM-25, 0061).
BEGIN;
DO $$
DECLARE
    c_now constant timestamptz := '2030-01-15 12:00:00+00';
    c_start constant timestamptz := '2030-02-01 18:00:00+00';
    c_opens constant timestamptz := '2030-01-10 09:00:00+00';
    c_closes constant timestamptz := '2030-01-20 09:00:00+00';
    v_owner uuid;
    v_att uuid[] := ARRAY[]::uuid[];
    v_id uuid;
    v_event uuid;
    v_small uuid;
    v_cancelled uuid;
    v_reg public.event_registrations;
    v_other public.event_registrations;
    v_row public.event_registrations;
    v_first timestamptz;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;
    FOR i IN 1..4 LOOP
        v_id := gen_random_uuid();
        INSERT INTO auth.users (id) VALUES (v_id);
        v_att := v_att || v_id;
    END LOOP;

    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-22 open', 'Draft', ARRAY[c_start], c_opens, c_closes, 10)
    RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-22 small', 'Draft', ARRAY[c_start], c_opens, c_closes, 1)
    RETURNING id INTO v_small;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-22 cancelled', 'Draft', ARRAY[c_start], c_opens, c_closes, 5)
    RETURNING id INTO v_cancelled;
    UPDATE public.event_requests SET status = 'Confirmed'
        WHERE id IN (v_event, v_small, v_cancelled);

    v_reg := public.register_for_event(v_event, v_att[1], c_now);
    v_other := public.register_for_event(v_event, v_att[2], c_now);

    -- AC1-H1 (happy): withdrawing sets Withdrawn and withdrawn_at, returns the row, touches no other row.
    v_row := public.withdraw_registration(v_reg.id, v_att[1], c_now);
    ASSERT v_row.id = v_reg.id AND v_row.status = 'Withdrawn' AND v_row.withdrawn_at = c_now,
        'AC1-H1: withdrawal result wrong';
    ASSERT (SELECT status FROM public.event_registrations WHERE id = v_reg.id) = 'Withdrawn',
        'AC1-H1: row not stored as Withdrawn';
    ASSERT (SELECT status FROM public.event_registrations WHERE id = v_other.id) = 'Registered'
        AND (SELECT withdrawn_at FROM public.event_registrations WHERE id = v_other.id) IS NULL,
        'AC1-H1: another registration was touched';

    -- AC2-N1 (negative): withdrawing again is P0004 'already withdrawn' and keeps withdrawn_at.
    BEGIN
        PERFORM public.withdraw_registration(v_reg.id, v_att[1], c_now + interval '1 hour');
        RAISE EXCEPTION 'AC2-N1: second withdrawal was accepted';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'already withdrawn', 'AC2-N1: wrong reason ' || SQLERRM;
    END;
    ASSERT (SELECT withdrawn_at FROM public.event_registrations WHERE id = v_reg.id) = c_now,
        'AC2-N1: withdrawn_at changed';

    -- AC2-N2 (negative): another attendee's registration is P0002 and unchanged.
    BEGIN
        PERFORM public.withdraw_registration(v_other.id, v_att[3], c_now);
        RAISE EXCEPTION 'AC2-N2: a stranger withdrew someone else''s registration';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
    ASSERT (SELECT status FROM public.event_registrations WHERE id = v_other.id) = 'Registered',
        'AC2-N2: row changed';

    -- AC2-N3 (negative): an unknown id is P0002.
    BEGIN
        PERFORM public.withdraw_registration(gen_random_uuid(), v_att[1], c_now);
        RAISE EXCEPTION 'AC2-N3: unknown id was accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;

    -- AC1-B1 / B2 (boundary): one second before the start is allowed, exactly at the start is refused.
    BEGIN
        PERFORM public.withdraw_registration(v_other.id, v_att[2], c_start);
        RAISE EXCEPTION 'AC1-B2: withdrawal at the start was accepted';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'withdrawal not permitted', 'AC1-B2: wrong reason ' || SQLERRM;
    END;
    ASSERT (SELECT status FROM public.event_registrations WHERE id = v_other.id) = 'Registered',
        'AC1-B2: refused call changed the row';
    v_row := public.withdraw_registration(v_other.id, v_att[2], c_start - interval '1 second');
    ASSERT v_row.status = 'Withdrawn', 'AC1-B1: withdrawal one second before start refused';

    -- AC1-H2 (happy): after the registration window closed but before the start.
    v_reg := public.register_for_event(v_event, v_att[3], c_now);
    UPDATE public.event_requests SET registration_closes_at = c_now - interval '1 day' WHERE id = v_event;
    v_row := public.withdraw_registration(v_reg.id, v_att[3], c_now);
    ASSERT v_row.status = 'Withdrawn', 'AC1-H2: withdrawal after window close refused';
    UPDATE public.event_requests SET registration_closes_at = c_closes WHERE id = v_event;

    -- AC1-B4 (boundary): a multi-date event is cut off at its earliest date.
    v_reg := public.register_for_event(v_event, v_att[4], c_now);
    UPDATE public.event_requests SET proposed_date_times = ARRAY[c_start + interval '2 days', c_start]
        WHERE id = v_event;
    BEGIN
        PERFORM public.withdraw_registration(v_reg.id, v_att[4], c_start + interval '1 day');
        RAISE EXCEPTION 'AC1-B4: withdrawal after the earliest date was accepted';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;

    -- AC1-B5 (boundary): the cut-off is read from the current event row, so a date change applies at once.
    UPDATE public.event_requests SET proposed_date_times = ARRAY[c_now - interval '1 day'] WHERE id = v_event;
    BEGIN
        PERFORM public.withdraw_registration(v_reg.id, v_att[4], c_now);
        RAISE EXCEPTION 'AC1-B5: withdrawal after the event moved earlier was accepted';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    UPDATE public.event_requests SET proposed_date_times = ARRAY[c_start] WHERE id = v_event;
    v_row := public.withdraw_registration(v_reg.id, v_att[4], c_now);
    ASSERT v_row.status = 'Withdrawn', 'AC1-B5: withdrawal after the event moved later refused';

    -- AC2-P1 (partition): a Cancelled event refuses, and the row stays Registered.
    v_reg := public.register_for_event(v_cancelled, v_att[1], c_now);
    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_cancelled;
    BEGIN
        PERFORM public.withdraw_registration(v_reg.id, v_att[1], c_now);
        RAISE EXCEPTION 'AC2-P1: withdrawal for a Cancelled event was accepted';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'withdrawal not permitted', 'AC2-P1: wrong reason ' || SQLERRM;
    END;
    ASSERT (SELECT status FROM public.event_registrations WHERE id = v_reg.id) = 'Registered',
        'AC2-P1: refused call changed the row';

    -- AC3-H2 / AC3-H3 (happy): the freed place can be taken, and the withdrawn attendee can register again.
    v_reg := public.register_for_event(v_small, v_att[1], c_now);
    BEGIN
        PERFORM public.register_for_event(v_small, v_att[2], c_now);
        RAISE EXCEPTION 'AC3-H2: event not full before withdrawal';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    PERFORM public.withdraw_registration(v_reg.id, v_att[1], c_now);
    v_row := public.register_for_event(v_small, v_att[2], c_now);
    ASSERT v_row.status = 'Registered', 'AC3-H2: freed place could not be taken';
    PERFORM public.withdraw_registration(v_row.id, v_att[2], c_now);
    v_row := public.register_for_event(v_small, v_att[1], c_now);
    ASSERT v_row.id <> v_reg.id AND v_row.status = 'Registered', 'AC3-H3: re-registration failed';
    ASSERT (SELECT count(*) FROM public.event_registrations
        WHERE event_request_id = v_small AND status = 'Registered') = 1, 'AC3-H2: more than one active row';
    ASSERT (SELECT status FROM public.event_registrations WHERE id = v_reg.id) = 'Withdrawn',
        'AC3-H3: the old Withdrawn row was not kept';

    -- AC4-X1 (cross-cutting): the CHECKs pair status and withdrawn_at and limit the values.
    BEGIN
        UPDATE public.event_registrations SET status = 'Withdrawn' WHERE id = v_row.id;
        RAISE EXCEPTION 'AC4-X1: Withdrawn without withdrawn_at was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE public.event_registrations SET withdrawn_at = c_now WHERE id = v_row.id;
        RAISE EXCEPTION 'AC4-X1: withdrawn_at on a Registered row was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE public.event_registrations SET status = 'Waiting' WHERE id = v_row.id;
        RAISE EXCEPTION 'AC4-X1: unknown status was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    -- AC2-X3 (cross-cutting): browser roles cannot call the function or update the table.
    ASSERT NOT has_function_privilege('anon',
        'public.withdraw_registration(uuid, uuid, timestamptz)', 'EXECUTE'), 'AC2-X3: anon can execute';
    ASSERT NOT has_function_privilege('authenticated',
        'public.withdraw_registration(uuid, uuid, timestamptz)', 'EXECUTE'), 'AC2-X3: authenticated can execute';
    ASSERT has_function_privilege('service_role',
        'public.withdraw_registration(uuid, uuid, timestamptz)', 'EXECUTE'), 'AC2-X3: service_role lost execute';
    ASSERT NOT has_column_privilege('anon', 'public.event_registrations', 'status', 'UPDATE'),
        'AC2-X3: anon can update status';
    ASSERT NOT has_column_privilege('authenticated', 'public.event_registrations', 'status', 'UPDATE'),
        'AC2-X3: authenticated can update status';
    ASSERT has_column_privilege('service_role', 'public.event_registrations', 'status', 'UPDATE')
        AND has_column_privilege('service_role', 'public.event_registrations', 'withdrawn_at', 'UPDATE'),
        'AC2-X3: service_role cannot update status/withdrawn_at';
    ASSERT NOT has_column_privilege('service_role', 'public.event_registrations', 'attendee_id', 'UPDATE'),
        'AC2-X3: service_role can rewrite attendee_id';

    RAISE NOTICE 'ALL REGISTRATION WITHDRAWAL VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
