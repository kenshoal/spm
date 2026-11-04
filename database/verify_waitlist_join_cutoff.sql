-- SCRUM-24 hotfix: joining closes at the cut-off (start - 72h), the instant the
-- timer closes the list (AC10). Run after 0093. Rolls back; prints
-- WAITLIST JOIN CUT-OFF VERIFICATIONS PASSED.
-- AC1-B5..B7 (boundary, D layer) and AC1-N5's database side.
BEGIN;
DO $$
DECLARE
    c_start constant timestamptz := '2030-02-10 10:00:00+00';
    c_cutoff constant timestamptz := '2030-02-07 10:00:00+00';  -- start - 72h
    v_owner uuid;
    v_holder uuid := gen_random_uuid();
    v_a uuid := gen_random_uuid();
    v_b uuid := gen_random_uuid();
    v_c uuid := gen_random_uuid();
    v_event uuid;
    v_entry public.event_waitlist_entries;
    v_refused boolean;
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN
        RAISE EXCEPTION 'Verification requires an existing auth user';
    END IF;
    INSERT INTO auth.users (id) VALUES (v_holder), (v_a), (v_b), (v_c);

    -- Registration stays open past the start, as on the event that exposed this.
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 join cut-off', 'Draft', ARRAY[c_start],
        '2030-01-01 00:00:00+00', c_start + interval '2 days', 1)
    RETURNING id INTO v_event;
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;
    PERFORM public.register_for_event(v_event, v_holder, '2030-01-02 00:00:00+00');

    -- AC1-B5: one second before the cut-off the join is accepted.
    v_entry := public.join_waitlist(v_event, v_a, c_cutoff - interval '1 second');
    ASSERT v_entry.status = 'Waiting', 'AC1-B5: join before the cut-off not Waiting';

    -- AC1-B6: at the cut-off instant it is refused (P0004 'waitlist closed').
    v_refused := false;
    BEGIN
        PERFORM public.join_waitlist(v_event, v_b, c_cutoff);
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'waitlist closed', 'AC1-B6: wrong refusal: ' || SQLERRM;
        v_refused := true;
    END;
    ASSERT v_refused, 'AC1-B6: join at the cut-off was accepted';

    -- AC1-B7: after the event has started it is refused too.
    v_refused := false;
    BEGIN
        PERFORM public.join_waitlist(v_event, v_c, c_start + interval '1 second');
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'waitlist closed', 'AC1-B7: wrong refusal: ' || SQLERRM;
        v_refused := true;
    END;
    ASSERT v_refused, 'AC1-B7: join after the start was accepted';

    -- AC1-N5 (forbidden side effect): the refused joins stored nothing.
    ASSERT (SELECT count(*) FROM public.event_waitlist_entries
            WHERE event_request_id = v_event AND attendee_id IN (v_b, v_c)) = 0,
        'AC1-N5: a refused join stored an entry';

    RAISE NOTICE 'WAITLIST JOIN CUT-OFF VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
