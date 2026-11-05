-- SCRUM-24 hotfix: a registration withdrawal hands the freed place to the waiting list
-- (AC2-H1), and keeps SCRUM-25's check-in refusal. Run after 0094. Rolls back; prints
-- WITHDRAWAL WAITLIST HAND-OVER VERIFICATIONS PASSED.
-- Guards against 0067 being applied after the waiting list, which replaced
-- withdraw_registration with a version that never opens the place.
BEGIN;
DO $$
DECLARE
    c_start constant timestamptz := '2030-02-10 10:00:00+00';
    v_owner uuid;
    v_holder uuid := gen_random_uuid();
    v_a uuid := gen_random_uuid();
    v_event uuid;
    v_refused boolean;
    v_reg public.event_registrations;
    v_src text;
BEGIN
    -- Both behaviours are in the live function body.
    SELECT prosrc INTO v_src FROM pg_proc
    WHERE proname = 'withdraw_registration' AND pronamespace = 'public'::regnamespace;
    ASSERT v_src LIKE '%already checked in%', 'withdraw_registration lost the SCRUM-25 check-in refusal';
    ASSERT v_src LIKE '%open_place%', 'withdraw_registration lost the waiting-list hand-over (AC2-H1)';

    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN
        RAISE EXCEPTION 'Verification requires an existing auth user';
    END IF;
    INSERT INTO auth.users (id) VALUES (v_holder), (v_a);
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 hand-over', 'Draft', ARRAY[c_start],
        '2030-01-01 00:00:00+00', '2030-02-01 00:00:00+00', 1)
    RETURNING id INTO v_event;
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;

    -- AC2-H1 (D layer): the withdrawal offers the place to the waiting attendee.
    v_reg := public.register_for_event(v_event, v_holder, '2030-01-02 00:00:00+00');
    PERFORM public.join_waitlist(v_event, v_a, '2030-01-03 00:00:00+00');
    PERFORM public.withdraw_registration(v_reg.id, v_holder, '2030-01-04 00:00:00+00');
    ASSERT (SELECT status FROM public.event_waitlist_entries
            WHERE event_request_id = v_event AND attendee_id = v_a) = 'Offered',
        'AC2-H1: the withdrawal did not offer the place to the waiting attendee';
    ASSERT (SELECT count(*) FROM public.event_waitlist_places WHERE event_request_id = v_event) = 1,
        'AC2-H1: the withdrawal did not open exactly one place';

    -- SCRUM-25 (0067): a checked-in attendee still cannot withdraw.
    -- A accepts the offered place, is checked in, then tries to withdraw.
    PERFORM public.accept_waitlist_offer(
        (SELECT id FROM public.event_waitlist_entries WHERE event_request_id = v_event AND attendee_id = v_a),
        v_a, '2030-01-05 00:00:00+00');
    SELECT * INTO v_reg FROM public.event_registrations
    WHERE event_request_id = v_event AND attendee_id = v_a AND status = 'Registered';
    UPDATE public.event_registrations SET attended_at = '2030-01-06 00:00:00+00' WHERE id = v_reg.id;
    v_refused := false;
    BEGIN
        PERFORM public.withdraw_registration(v_reg.id, v_a, '2030-01-07 00:00:00+00');
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'already checked in', 'SCRUM-25: wrong refusal: ' || SQLERRM;
        v_refused := true;
    END;
    ASSERT v_refused, 'SCRUM-25: a checked-in attendee could withdraw';

    RAISE NOTICE 'WITHDRAWAL WAITLIST HAND-OVER VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
