-- SCRUM-25: real Postgres evidence for coordinator check-in; every fixture rolls back.
-- Run after 0062 (withdrawal) and 0061, the order on dev and shared. Prints ALL EVENT ATTENDANCE VERIFICATIONS PASSED.
BEGIN;
DO $$
DECLARE
    -- Event at 1 Feb 2030 18:00 SGT (10:00 UTC).
    c_day constant timestamptz := '2030-02-01 18:00:00+08';
    c_noon constant timestamptz := '2030-02-01 12:00:00+08';
    v_owner uuid;
    v_c1 text := gen_random_uuid()::text;
    v_c2 text := gen_random_uuid()::text;
    v_att uuid[] := ARRAY[]::uuid[];
    v_id uuid;
    v_event uuid;
    v_multi uuid;
    v_early uuid;
    v_nodates uuid;
    v_planning uuid;
    v_other uuid;
    v_reassigned uuid;
    v_full uuid;
    v_reg uuid[] := ARRAY[]::uuid[];
    v_row public.event_registrations;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;
    FOR i IN 1..10 LOOP
        v_id := gen_random_uuid();
        INSERT INTO auth.users (id) VALUES (v_id);
        v_att := v_att || v_id;
    END LOOP;

    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity, proposed_date_times)
    VALUES (v_owner, 'VERIFY SCRUM-25 day', 'Draft', 10, ARRAY[c_day]) RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity, proposed_date_times)
    VALUES (v_owner, 'VERIFY SCRUM-25 two days', 'Draft', 10, ARRAY[c_day, c_day + interval '1 day']) RETURNING id INTO v_multi;
    -- 1 Feb 2030 01:00 SGT is 31 Jan 17:00 UTC: proves the day is judged in Singapore.
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity, proposed_date_times)
    VALUES (v_owner, 'VERIFY SCRUM-25 early', 'Draft', 10, ARRAY['2030-02-01 01:00:00+08'::timestamptz]) RETURNING id INTO v_early;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-25 no dates', 'Draft', 10) RETURNING id INTO v_nodates;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity, proposed_date_times)
    VALUES (v_owner, 'VERIFY SCRUM-25 planning', 'Draft', 10, ARRAY[c_day]) RETURNING id INTO v_planning;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity, proposed_date_times)
    VALUES (v_owner, 'VERIFY SCRUM-25 other', 'Draft', 10, ARRAY[c_day]) RETURNING id INTO v_other;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity, proposed_date_times)
    VALUES (v_owner, 'VERIFY SCRUM-25 reassigned', 'Draft', 10, ARRAY[c_day]) RETURNING id INTO v_reassigned;
    INSERT INTO public.event_requests (organiser_id, event_name, status, registration_capacity, proposed_date_times)
    VALUES (v_owner, 'VERIFY SCRUM-25 full', 'Draft', 1, ARRAY[c_day]) RETURNING id INTO v_full;
    UPDATE public.event_requests SET status = 'Confirmed'
    WHERE id IN (v_event, v_multi, v_early, v_nodates, v_other, v_reassigned, v_full);
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_planning;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    SELECT e, v_c1, v_owner::text
    FROM unnest(ARRAY[v_event, v_multi, v_early, v_nodates, v_planning, v_other, v_reassigned, v_full]) AS e;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    VALUES (v_reassigned, v_c2, v_owner::text);

    -- One registration per (event, attendee) fixture, inserted directly.
    INSERT INTO public.event_registrations (event_request_id, attendee_id)
    VALUES (v_event, v_att[1]), (v_event, v_att[2]), (v_multi, v_att[3]), (v_early, v_att[4]),
           (v_nodates, v_att[5]), (v_planning, v_att[6]), (v_other, v_att[7]),
           (v_reassigned, v_att[8]), (v_full, v_att[9]), (v_event, v_att[10]);
    SELECT array_agg(id ORDER BY attendee_id = v_att[1] DESC, attendee_id = v_att[2] DESC) INTO v_reg
    FROM public.event_registrations WHERE event_request_id = v_event;

    -- AC1-H1, AC2 (happy): checked in on the event day; status stays Registered.
    v_row := public.check_in_attendee(v_event, v_reg[1], v_c1, c_noon);
    ASSERT v_row.attended_at = c_noon AND v_row.checked_in_by::text = v_c1, 'AC1-H1: check-in not recorded';
    ASSERT v_row.status = 'Registered', 'AC2: status changed on check-in';
    ASSERT (SELECT attended_at IS NULL FROM public.event_registrations WHERE id = v_reg[2]),
        'AC1-H1: another registration was changed';

    -- AC4-N3, AC4-X1 (negative): a second check-in of the same row is refused and changes nothing.
    BEGIN
        PERFORM public.check_in_attendee(v_event, v_reg[1], v_c1, c_noon + interval '1 hour');
        RAISE EXCEPTION 'AC4-N3: checked in twice';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'already checked in', 'AC4-N3: wrong message ' || SQLERRM;
    END;
    ASSERT (SELECT attended_at = c_noon FROM public.event_registrations WHERE id = v_reg[1]),
        'AC4-N3: refused check-in changed attended_at';

    -- AC3-N1 (negative): a checked-in attendee can't withdraw (0067), even before the start time.
    BEGIN
        PERFORM public.withdraw_registration(v_reg[1], v_att[1], c_noon + interval '1 hour');
        RAISE EXCEPTION 'AC3-N1: withdrew a checked-in registration';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'already checked in', 'AC3-N1: wrong message ' || SQLERRM;
    END;
    ASSERT (SELECT status = 'Registered' AND withdrawn_at IS NULL AND attended_at = c_noon
            FROM public.event_registrations WHERE id = v_reg[1]),
        'AC3-N1: refused withdrawal changed the registration';

    -- AC1-B1 (boundary): 23:59:59 SGT the day before is refused.
    BEGIN
        PERFORM public.check_in_attendee(v_event, v_reg[2], v_c1, '2030-01-31 23:59:59+08');
        RAISE EXCEPTION 'AC1-B1: checked in the day before';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'not event day', 'AC1-B1: wrong message ' || SQLERRM;
    END;
    -- AC1-B3 (boundary): 00:00:00 SGT the day after is refused.
    BEGIN
        PERFORM public.check_in_attendee(v_event, v_reg[2], v_c1, '2030-02-02 00:00:00+08');
        RAISE EXCEPTION 'AC1-B3: checked in the day after';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'not event day', 'AC1-B3: wrong message ' || SQLERRM;
    END;
    -- AC1-B2 (boundary): 00:00:00 SGT on the day is allowed.
    v_row := public.check_in_attendee(v_event, v_reg[2], v_c1, '2030-02-01 00:00:00+08');
    ASSERT v_row.attended_at = '2030-02-01 00:00:00+08', 'AC1-B2: midnight check-in refused';

    -- AC1-P1 (partition): the second day of a two-day event.
    v_row := public.check_in_attendee(v_multi,
        (SELECT id FROM public.event_registrations WHERE event_request_id = v_multi), v_c1, c_noon + interval '1 day');
    ASSERT v_row.attended_at IS NOT NULL, 'AC1-P1: second-day check-in refused';

    -- AC1-X1 (cross-cutting): Singapore date, not UTC. 31 Jan 20:00 SGT is the UTC date of the
    -- event (31 Jan) but not its Singapore date (1 Feb), so it is refused.
    BEGIN
        PERFORM public.check_in_attendee(v_early,
            (SELECT id FROM public.event_registrations WHERE event_request_id = v_early), v_c1, '2030-01-31 20:00:00+08');
        RAISE EXCEPTION 'AC1-X1: UTC date used';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'not event day', 'AC1-X1: wrong message ' || SQLERRM;
    END;
    v_row := public.check_in_attendee(v_early,
        (SELECT id FROM public.event_registrations WHERE event_request_id = v_early), v_c1, '2030-02-01 08:00:00+08');
    ASSERT v_row.attended_at IS NOT NULL, 'AC1-X1: Singapore event day refused';

    -- AC1-N3 (negative): an event with no dates has no event day.
    BEGIN
        PERFORM public.check_in_attendee(v_nodates,
            (SELECT id FROM public.event_registrations WHERE event_request_id = v_nodates), v_c1, c_noon);
        RAISE EXCEPTION 'AC1-N3: checked in without dates';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'not event day', 'AC1-N3: wrong message ' || SQLERRM;
    END;

    -- AC1-N1 (negative): the event isn't Confirmed.
    BEGIN
        PERFORM public.check_in_attendee(v_planning,
            (SELECT id FROM public.event_registrations WHERE event_request_id = v_planning), v_c1, c_noon);
        RAISE EXCEPTION 'AC1-N1: checked in on a Planning event';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'event not found', 'AC1-N1: wrong message ' || SQLERRM;
    END;

    -- AC1-N4 (negative): a coordinator reassigned away is refused at mutation time.
    BEGIN
        PERFORM public.check_in_attendee(v_reassigned,
            (SELECT id FROM public.event_registrations WHERE event_request_id = v_reassigned), v_c1, c_noon);
        RAISE EXCEPTION 'AC1-N4: reassigned coordinator checked in';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'event not found', 'AC1-N4: wrong message ' || SQLERRM;
    END;

    -- AC4-N1 (negative): a registration from another event.
    BEGIN
        PERFORM public.check_in_attendee(v_event,
            (SELECT id FROM public.event_registrations WHERE event_request_id = v_other), v_c1, c_noon);
        RAISE EXCEPTION 'AC4-N1: checked in another event''s registration';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'registration not found', 'AC4-N1: wrong message ' || SQLERRM;
    END;

    -- AC2-H1 (happy): a checked-in attendee still holds their place.
    PERFORM public.check_in_attendee(v_full,
        (SELECT id FROM public.event_registrations WHERE event_request_id = v_full), v_c1, c_noon);
    UPDATE public.event_requests SET registration_opens_at = c_noon - interval '1 day',
        registration_closes_at = c_noon + interval '1 day' WHERE id = v_full;
    BEGIN
        PERFORM public.register_for_event(v_full, v_att[10], c_noon);
        RAISE EXCEPTION 'AC2-H1: check-in freed the place';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'event full', 'AC2-H1: wrong message ' || SQLERRM;
    END;

    -- AC4-N4 (negative): a withdrawn registration (SCRUM-22, 0062) can't be checked in.
    UPDATE public.event_registrations SET status = 'Withdrawn', withdrawn_at = now()
    WHERE event_request_id = v_event AND attendee_id = v_att[10];
    BEGIN
        PERFORM public.check_in_attendee(v_event,
            (SELECT id FROM public.event_registrations WHERE event_request_id = v_event AND attendee_id = v_att[10]),
            v_c1, c_noon);
        RAISE EXCEPTION 'AC4-N4: checked in a withdrawn registration';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN
        ASSERT SQLERRM = 'registration not found', 'AC4-N4: wrong message ' || SQLERRM;
    END;
    ASSERT (SELECT attended_at IS NULL FROM public.event_registrations
        WHERE event_request_id = v_event AND attendee_id = v_att[10]), 'AC4-N4: withdrawn row changed';
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_registrations
        WHERE event_request_id IN (v_nodates, v_planning, v_other, v_reassigned) AND attended_at IS NOT NULL),
        'refusals stored a check-in';

    -- AC1-X4 (cross-cutting): browser roles can't run the function.
    ASSERT NOT has_function_privilege('anon', 'public.check_in_attendee(uuid, uuid, text, timestamptz)', 'EXECUTE'),
        'AC1-X4: anon can execute';
    ASSERT NOT has_function_privilege('authenticated', 'public.check_in_attendee(uuid, uuid, text, timestamptz)', 'EXECUTE'),
        'AC1-X4: authenticated can execute';
    ASSERT has_function_privilege('service_role', 'public.check_in_attendee(uuid, uuid, text, timestamptz)', 'EXECUTE'),
        'AC1-X4: service_role cannot execute';

    RAISE NOTICE 'ALL EVENT ATTENDANCE VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
