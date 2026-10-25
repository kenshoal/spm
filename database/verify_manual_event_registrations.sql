-- SCRUM-41: real Postgres evidence for coordinator-entered registrations; every fixture rolls back.
-- Run after 0060. Prints ALL MANUAL REGISTRATION VERIFICATIONS PASSED.
-- The local auth.users test double needs email and raw_app_meta_data columns (genuine Supabase Auth has both).
BEGIN;
DO $$
DECLARE
    c_now constant timestamptz := '2030-01-15 12:00:00+00';
    v_owner uuid;
    v_c1 text := gen_random_uuid()::text;
    v_c2 text := gen_random_uuid()::text;
    v_vip uuid := gen_random_uuid();
    v_self uuid := gen_random_uuid();
    v_staff uuid := gen_random_uuid();
    v_meta uuid := gen_random_uuid();
    v_event uuid;
    v_closed uuid;
    v_small uuid;
    v_nocap uuid;
    v_planning uuid;
    v_reassigned uuid;
    v_row public.event_registrations;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;
    -- No staff_roles row and empty metadata: an attendee by default (D3).
    INSERT INTO auth.users (id, email) VALUES (v_vip, 'vip41@test.local'), (v_self, 'self41@test.local');
    INSERT INTO auth.users (id, email) VALUES (v_staff, 'staff41@test.local');
    INSERT INTO public.staff_roles (user_id, role) VALUES (v_staff, 'venue_staff');
    INSERT INTO auth.users (id, email, raw_app_meta_data)
    VALUES (v_meta, 'meta41@test.local', '{"roles": ["event_organiser"]}');

    -- Confirmed fixtures set directly, as in verify_event_registrations.sql.
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-41 open', 'Draft', c_now - interval '1 day', c_now + interval '1 day', 10)
    RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-41 closed', 'Draft', c_now - interval '9 days', c_now - interval '8 days', 10)
    RETURNING id INTO v_closed;
    INSERT INTO public.event_requests (organiser_id, event_name, status,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-41 small', 'Draft', c_now - interval '1 day', c_now + interval '1 day', 2)
    RETURNING id INTO v_small;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
    VALUES (v_owner, 'VERIFY SCRUM-41 no capacity', 'Draft') RETURNING id INTO v_nocap;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-41 planning', 'Draft', 10) RETURNING id INTO v_planning;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-41 reassigned', 'Draft', 10) RETURNING id INTO v_reassigned;
    UPDATE public.event_requests SET status = 'Confirmed'
    WHERE id IN (v_event, v_closed, v_small, v_nocap, v_reassigned);
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_planning;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    SELECT e, v_c1, v_owner::text FROM unnest(ARRAY[v_event, v_closed, v_small, v_nocap, v_planning, v_reassigned]) AS e;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    VALUES (v_reassigned, v_c2, v_owner::text);

    -- AC1-H1, AC4-H1 (happy): the assigned coordinator registers an attendee by email.
    v_row := public.coordinator_register_attendee(v_event, v_c1, 'vip41@test.local');
    ASSERT v_row.attendee_id = v_vip AND v_row.status = 'Registered', 'AC1-H1: wrong row';
    ASSERT v_row.registered_by::text = v_c1, 'AC4-H1: registered_by is not the coordinator';
    -- AC4-H1 (happy): a self-registration keeps registered_by null.
    v_row := public.register_for_event(v_event, v_self, c_now);
    ASSERT v_row.registered_by IS NULL, 'AC4-H1: self-registration has registered_by';

    -- AC1-H2 (happy): outside the window is allowed for a coordinator (D2).
    v_row := public.coordinator_register_attendee(v_closed, v_c1, 'vip41@test.local');
    ASSERT v_row.event_request_id = v_closed, 'AC1-H2: closed-window registration refused';

    -- AC1-P1 (partition): the email match ignores case.
    v_row := public.coordinator_register_attendee(v_small, v_c1, 'VIP41@Test.Local');
    ASSERT v_row.attendee_id = v_vip, 'AC1-P1: case-insensitive match failed';
    -- AC2-B1 (boundary): one place left is taken (1 of 2 registered before this call).
    v_row := public.coordinator_register_attendee(v_small, v_c1, 'self41@test.local');
    ASSERT (SELECT count(*) = 2 FROM public.event_registrations WHERE event_request_id = v_small),
        'AC2-B1: last place not taken';

    -- AC2-B2 (boundary): exactly full is refused and nothing is stored.
    INSERT INTO auth.users (id, email) VALUES (gen_random_uuid(), 'late41@test.local');
    BEGIN
        PERFORM public.coordinator_register_attendee(v_small, v_c1, 'late41@test.local');
        RAISE EXCEPTION 'AC2-B2: registered past capacity';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'event full', 'AC2-B2: wrong message ' || SQLERRM;
    END;
    ASSERT (SELECT count(*) = 2 FROM public.event_registrations WHERE event_request_id = v_small),
        'AC2-B2: refused registration changed the count';

    -- AC2-X1 (cross-cutting): a manual registration takes a place self-registration can't then take.
    UPDATE public.event_requests SET registration_capacity = 3 WHERE id = v_small;
    PERFORM public.coordinator_register_attendee(v_small, v_c1, 'late41@test.local');
    BEGIN
        PERFORM public.register_for_event(v_small, gen_random_uuid(), c_now);
        RAISE EXCEPTION 'AC2-X1: self-registration took a place a coordinator filled';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'event full', 'AC2-X1: wrong message ' || SQLERRM;
    END;

    -- AC2-N1 (negative): no capacity set.
    BEGIN
        PERFORM public.coordinator_register_attendee(v_nocap, v_c1, 'vip41@test.local');
        RAISE EXCEPTION 'AC2-N1: registered without a capacity';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'capacity not set', 'AC2-N1: wrong message ' || SQLERRM;
    END;

    -- AC1-N5 (negative): duplicate active registration.
    BEGIN
        PERFORM public.coordinator_register_attendee(v_event, v_c1, 'vip41@test.local');
        RAISE EXCEPTION 'AC1-N5: duplicate registration succeeded';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'already registered', 'AC1-N5: wrong message ' || SQLERRM;
    END;

    -- AC1-N1 (negative): unknown email.
    BEGIN
        PERFORM public.coordinator_register_attendee(v_event, v_c1, 'nobody41@test.local');
        RAISE EXCEPTION 'AC1-N1: unknown email registered';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'attendee not found', 'AC1-N1: wrong message ' || SQLERRM;
    END;

    -- AC1-N2 (negative): an account whose effective roles exclude attendee, via staff_roles and via metadata.
    BEGIN
        PERFORM public.coordinator_register_attendee(v_event, v_c1, 'staff41@test.local');
        RAISE EXCEPTION 'AC1-N2: venue staff registered as attendee';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'attendee not found', 'AC1-N2: wrong message ' || SQLERRM;
    END;
    BEGIN
        PERFORM public.coordinator_register_attendee(v_event, v_c1, 'meta41@test.local');
        RAISE EXCEPTION 'AC1-N2: organiser registered as attendee';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'attendee not found', 'AC1-N2: wrong message ' || SQLERRM;
    END;

    -- AC1-N3 (negative): the event isn't Confirmed.
    BEGIN
        PERFORM public.coordinator_register_attendee(v_planning, v_c1, 'vip41@test.local');
        RAISE EXCEPTION 'AC1-N3: registered for a Planning event';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'event not found', 'AC1-N3: wrong message ' || SQLERRM;
    END;

    -- AC4-N1 (negative): a coordinator reassigned away is refused at mutation time.
    BEGIN
        PERFORM public.coordinator_register_attendee(v_reassigned, v_c1, 'vip41@test.local');
        RAISE EXCEPTION 'AC4-N1: reassigned coordinator registered an attendee';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'event not found', 'AC4-N1: wrong message ' || SQLERRM;
    END;
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_registrations
        WHERE event_request_id IN (v_nocap, v_planning, v_reassigned)), 'refusals stored rows';

    -- AC4-X1 (cross-cutting): browser roles can't run the function or write registered_by.
    ASSERT NOT has_function_privilege('anon', 'public.coordinator_register_attendee(uuid, text, text)', 'EXECUTE'),
        'AC4-X1: anon can execute';
    ASSERT NOT has_function_privilege('authenticated', 'public.coordinator_register_attendee(uuid, text, text)', 'EXECUTE'),
        'AC4-X1: authenticated can execute';
    ASSERT has_function_privilege('service_role', 'public.coordinator_register_attendee(uuid, text, text)', 'EXECUTE'),
        'AC4-X1: service_role cannot execute';
    ASSERT NOT has_column_privilege('authenticated', 'public.event_registrations', 'registered_by', 'INSERT,UPDATE'),
        'AC4-X1: authenticated can write registered_by';

    RAISE NOTICE 'ALL MANUAL REGISTRATION VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
