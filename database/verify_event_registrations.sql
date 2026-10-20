-- SCRUM-21: real Postgres evidence for event registration; every fixture rolls back.
-- Run after 0048. Prints ALL EVENT REGISTRATION VERIFICATIONS PASSED.
-- The race for the last place (AC4-X1) needs two sessions: verify_event_registrations_race.sh.
BEGIN;
DO $$
DECLARE
    c_now constant timestamptz := '2030-01-15 12:00:00+00';
    c_opens constant timestamptz := '2030-01-10 09:00:00+00';
    c_closes constant timestamptz := '2030-01-20 09:00:00+00';
    v_owner uuid;
    v_att uuid[] := ARRAY[]::uuid[];
    v_id uuid;
    v_event uuid;
    v_full uuid;
    v_nowin uuid;
    v_nocap uuid;
    v_cancelled uuid;
    v_planning uuid;
    v_row public.event_registrations;
    v_state text;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;
    FOR i IN 1..8 LOOP
        v_id := gen_random_uuid();
        INSERT INTO auth.users (id) VALUES (v_id);
        v_att := v_att || v_id;
    END LOOP;

    -- Fixtures. No story writes Confirmed yet (SCRUM-60), so the fixtures set it directly.
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-21 open', 'Draft', c_opens, c_closes, 100)
    RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-21 small', 'Draft', c_opens, c_closes, 2)
    RETURNING id INTO v_full;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-21 no window', 'Draft', 5) RETURNING id INTO v_nowin;
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at)
    VALUES (v_owner, 'VERIFY SCRUM-21 no capacity', 'Draft', c_opens, c_closes)
    RETURNING id INTO v_nocap;
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-21 cancelled', 'Draft', c_opens, c_closes, 5)
    RETURNING id INTO v_cancelled;
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-21 planning', 'Draft', c_opens, c_closes, 5)
    RETURNING id INTO v_planning;
    UPDATE public.event_requests SET status = 'Confirmed'
        WHERE id IN (v_event, v_full, v_nowin, v_nocap, v_cancelled);
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_planning;

    -- AC5-H1 (happy): a registration is stored with attendee, event, Registered and created_at.
    v_row := public.register_for_event(v_event, v_att[1], c_now);
    ASSERT v_row.event_request_id = v_event AND v_row.attendee_id = v_att[1]
        AND v_row.status = 'Registered' AND v_row.created_at IS NOT NULL AND v_row.id IS NOT NULL,
        'AC5-H1: wrong registration returned';
    ASSERT (SELECT count(*) = 1 FROM public.event_registrations WHERE event_request_id = v_event),
        'AC5-H1: expected exactly one stored registration';

    -- AC5-N2 (negative): the same attendee twice is refused and one row remains.
    BEGIN
        PERFORM public.register_for_event(v_event, v_att[1], c_now);
        RAISE EXCEPTION 'AC5-N2: duplicate registration succeeded';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'already registered', 'AC5-N2: wrong message ' || SQLERRM;
    END;
    ASSERT (SELECT count(*) = 1 FROM public.event_registrations WHERE event_request_id = v_event),
        'AC5-N2: refused duplicate changed the row count';

    -- AC5-N2 (negative): the partial unique index also stops a direct duplicate insert.
    BEGIN
        INSERT INTO public.event_registrations (event_request_id, attendee_id)
        VALUES (v_event, v_att[1]);
        RAISE EXCEPTION 'AC5-N2: direct duplicate insert succeeded';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    -- AC3-B1 (boundary): one second before the window opens is refused.
    BEGIN
        PERFORM public.register_for_event(v_event, v_att[2], c_opens - interval '1 second');
        RAISE EXCEPTION 'AC3-B1: registered before the window opened';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'registration not open', 'AC3-B1: wrong message ' || SQLERRM;
    END;
    -- AC3-B2 (boundary): exactly at opens_at is allowed (inclusive).
    PERFORM public.register_for_event(v_event, v_att[2], c_opens);
    -- AC3-B3 (boundary): one second after opening is allowed.
    PERFORM public.register_for_event(v_event, v_att[3], c_opens + interval '1 second');
    -- AC3-B4 (boundary): one second before closing is allowed.
    PERFORM public.register_for_event(v_event, v_att[4], c_closes - interval '1 second');
    -- AC3-B5 (boundary): exactly at closes_at is refused (exclusive).
    BEGIN
        PERFORM public.register_for_event(v_event, v_att[5], c_closes);
        RAISE EXCEPTION 'AC3-B5: registered at the closing instant';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'registration not open', 'AC3-B5: wrong message ' || SQLERRM;
    END;
    -- AC3-B6 (boundary): one second after closing is refused.
    BEGIN
        PERFORM public.register_for_event(v_event, v_att[5], c_closes + interval '1 second');
        RAISE EXCEPTION 'AC3-B6: registered after the window closed';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    ASSERT (SELECT count(*) = 4 FROM public.event_registrations WHERE event_request_id = v_event),
        'AC3-B: expected exactly the four allowed registrations';

    -- AC3-N1 (negative): no window set is not open and stores nothing.
    BEGIN
        PERFORM public.register_for_event(v_nowin, v_att[1], c_now);
        RAISE EXCEPTION 'AC3-N1: registered with no window';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'registration not open', 'AC3-N1: wrong message ' || SQLERRM;
    END;
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_registrations WHERE event_request_id = v_nowin),
        'AC3-N1: refused call stored a row';

    -- AC4-N1 (negative): no capacity set is not open and stores nothing.
    BEGIN
        PERFORM public.register_for_event(v_nocap, v_att[1], c_now);
        RAISE EXCEPTION 'AC4-N1: registered with no capacity';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'registration not open', 'AC4-N1: wrong message ' || SQLERRM;
    END;
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_registrations WHERE event_request_id = v_nocap),
        'AC4-N1: refused call stored a row';

    -- AC4-B1/B2 (boundary): capacity 2 takes two registrations, the third is refused as full.
    PERFORM public.register_for_event(v_full, v_att[1], c_now);
    PERFORM public.register_for_event(v_full, v_att[2], c_now);
    BEGIN
        PERFORM public.register_for_event(v_full, v_att[3], c_now);
        RAISE EXCEPTION 'AC4-B2: registered beyond capacity';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'event full', 'AC4-B2: wrong message ' || SQLERRM;
    END;
    ASSERT (SELECT count(*) = 2 FROM public.event_registrations WHERE event_request_id = v_full),
        'AC4-B2: refused call changed the count';

    -- AC2-X1 (negative): a Cancelled event and a Planning event are not found, nothing stored.
    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_cancelled;
    BEGIN
        PERFORM public.register_for_event(v_cancelled, v_att[1], c_now);
        RAISE EXCEPTION 'AC2-X1: registered for a cancelled event';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
    BEGIN
        PERFORM public.register_for_event(v_planning, v_att[1], c_now);
        RAISE EXCEPTION 'AC2-X1: registered for a planning event';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
    BEGIN
        PERFORM public.register_for_event(gen_random_uuid(), v_att[1], c_now);
        RAISE EXCEPTION 'AC2-X1: registered for an unknown event';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_registrations
        WHERE event_request_id IN (v_cancelled, v_planning)), 'AC2-X1: refused call stored a row';

    -- D2 (negative): the window and capacity columns reject impossible values.
    BEGIN
        UPDATE public.event_requests SET registration_closes_at = registration_opens_at
            WHERE id = v_event;
        RAISE EXCEPTION 'D2: closes = opens was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE public.event_requests SET registration_capacity = 0 WHERE id = v_event;
        RAISE EXCEPTION 'D2: capacity 0 was accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;

    -- AC5-X3 (cross-cutting): browser roles cannot reach the function or the table.
    ASSERT NOT has_function_privilege('anon',
        'public.register_for_event(uuid, uuid, timestamptz)', 'EXECUTE'), 'AC5-X3: anon can execute';
    ASSERT NOT has_function_privilege('authenticated',
        'public.register_for_event(uuid, uuid, timestamptz)', 'EXECUTE'), 'AC5-X3: authenticated can execute';
    ASSERT has_function_privilege('service_role',
        'public.register_for_event(uuid, uuid, timestamptz)', 'EXECUTE'), 'AC5-X3: service_role lost execute';
    ASSERT NOT has_table_privilege('anon', 'public.event_registrations', 'SELECT'), 'AC5-X3: anon can select';
    ASSERT NOT has_table_privilege('authenticated', 'public.event_registrations', 'SELECT'),
        'AC5-X3: authenticated can select';
    ASSERT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.event_registrations'::regclass),
        'AC5-X3: RLS is off on event_registrations';

    RAISE NOTICE 'ALL EVENT REGISTRATION VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
