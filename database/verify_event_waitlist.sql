-- SCRUM-24: real Postgres evidence for the event waiting list; every fixture rolls back.
-- Run after the SCRUM-24 migration (00NN_event_waitlist.sql) and 0048, 0060, 0062.
-- Prints ALL EVENT WAITLIST VERIFICATIONS PASSED.
-- The races (AC2-X1, AC3-X1, AC7-X1, AC9-X1) need two sessions:
-- verify_event_waitlist_race.sh.
-- API-layer rows (401/403/404/409 mappings, the positionless listing) live in
-- backend/eventRequestService/tests; this script proves the database contract.
BEGIN;
DO $$
DECLARE
    c_t0 constant timestamptz := '2030-01-10 09:00:00+00';  -- the offer time
    c_start constant timestamptz := '2030-02-10 10:00:00+00';  -- E starts
    c_cutoff constant timestamptz := '2030-02-07 10:00:00+00';  -- start - 72h (D8/D11)
    c_opens constant timestamptz := '2030-01-01 00:00:00+00';
    c_closes constant timestamptz := '2030-01-31 00:00:00+00';
    c_late_start constant timestamptz := '2030-03-01 10:00:00+00';
    v_owner uuid;
    v_h uuid[] := ARRAY[]::uuid[];       -- registration holders H1..H8
    v_a uuid; v_b uuid; v_c uuid; v_d uuid;  -- waitlisted attendees
    v_f uuid; v_g uuid;                  -- bystanders for refused registrations
    v_k text;                            -- assigned Coordinator (varchar(64), like 0011)
    v_event uuid;      -- E: the main scenario, capacity 2
    v_eq uuid;         -- equal queued_at + the one-active-entry index
    v_small uuid;      -- lone waitlister (AC4-P1)
    v_empty uuid;      -- nobody waiting (AC2-N1)
    v_cutoff uuid;     -- the #116 cut-off (AC10, AC11)
    v_cancel uuid;     -- event cancelled (AC12)
    v_fail uuid;       -- forced promotion failure (AC2-N3)
    v_reg public.event_registrations;
    v_reg2 public.event_registrations;
    v_entry public.event_waitlist_entries;
    v_entry_b public.event_waitlist_entries;
    v_entry_c public.event_waitlist_entries;
    v_entry_d public.event_waitlist_entries;
    v_place uuid;
    v_place2 uuid;
    v_expired timestamptz;
    v_text text;
    v_uuid uuid;
    v_positions uuid[];
BEGIN
    SELECT id INTO v_owner FROM auth.users ORDER BY created_at LIMIT 1;
    IF v_owner IS NULL THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;
    FOR i IN 1..8 LOOP
        v_h := v_h || gen_random_uuid();
        INSERT INTO auth.users (id) VALUES (v_h[i]);
    END LOOP;
    v_a := gen_random_uuid(); INSERT INTO auth.users (id, email)
        VALUES (v_a, 'verify-scrum24-a@test.local');
    v_b := gen_random_uuid(); INSERT INTO auth.users (id, email)
        VALUES (v_b, 'verify-scrum24-b@test.local');
    v_c := gen_random_uuid(); INSERT INTO auth.users (id, email)
        VALUES (v_c, 'verify-scrum24-c@test.local');
    v_d := gen_random_uuid(); INSERT INTO auth.users (id, email)
        VALUES (v_d, 'verify-scrum24-d@test.local');
    v_f := gen_random_uuid(); INSERT INTO auth.users (id, email)
        VALUES (v_f, 'verify-scrum24-f@test.local');
    v_g := gen_random_uuid(); INSERT INTO auth.users (id, email)
        VALUES (v_g, 'verify-scrum24-g@test.local');
    v_k := gen_random_uuid()::text;

    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 main', 'Draft', ARRAY[c_start], c_opens, c_closes, 2)
    RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 equal queue', 'Draft', ARRAY[c_start], c_opens, c_closes, 1)
    RETURNING id INTO v_eq;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 lone', 'Draft', ARRAY[c_start], c_opens, c_closes, 1)
    RETURNING id INTO v_small;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 empty list', 'Draft', ARRAY[c_start], c_opens, c_closes, 1)
    RETURNING id INTO v_empty;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 cut-off', 'Draft', ARRAY[c_late_start], c_opens, c_closes, 1)
    RETURNING id INTO v_cutoff;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 cancelled', 'Draft', ARRAY[c_start], c_opens, c_closes, 2)
    RETURNING id INTO v_cancel;
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    VALUES (v_owner, 'VERIFY SCRUM-24 rollback', 'Draft', ARRAY[c_start], c_opens, c_closes, 1)
    RETURNING id INTO v_fail;
    UPDATE public.event_requests SET status = 'Confirmed'
        WHERE id IN (v_event, v_eq, v_small, v_empty, v_cutoff, v_cancel, v_fail);

    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_k, v_owner::text);

    -- AC8-B1..B3 (boundary): places_taken at the capacity boundary.
    -- 0 Registered + 0 Offered = 0; 1 + 0 = 1; 2 + 0 = 2.
    ASSERT private.places_taken(v_event) = 0, 'AC8-B1: empty event not 0';
    v_reg := public.register_for_event(v_event, v_h[1], c_t0);
    ASSERT private.places_taken(v_event) = 1, 'AC8-B1: one registrant not 1';
    v_reg2 := public.register_for_event(v_event, v_h[2], c_t0);
    ASSERT private.places_taken(v_event) = 2, 'AC8-B3: two registrants not 2';

    -- Joining (AC1-H1's database side; AC1-B1's full-event join succeeds).
    v_entry := public.join_waitlist(v_event, v_a, c_t0);
    PERFORM public.join_waitlist(v_event, v_b, c_t0 + interval '1 second');
    v_entry_c := public.join_waitlist(v_event, v_c, c_t0 + interval '2 seconds');
    v_entry_d := public.join_waitlist(v_event, v_d, c_t0 + interval '3 seconds');
    ASSERT v_entry.status = 'Waiting' AND v_entry.queued_at = c_t0, 'AC1-H1: join wrong';

    -- AC2-H1 (happy): withdrawing H1 offers the place to A in the same transaction.
    v_reg := public.withdraw_registration(v_reg.id, v_h[1], c_t0);
    ASSERT v_reg.status = 'Withdrawn', 'AC2-H1: withdrawal failed';
    SELECT * INTO v_entry FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND attendee_id = v_a;
    ASSERT v_entry.status = 'Offered' AND v_entry.offered_at = c_t0,
        'AC2-H1: A not offered at T0';
    ASSERT v_entry.expires_at = c_t0 + interval '72 hours', 'AC2-H1: wrong expiry (D1)';
    v_place := v_entry.place_id;
    ASSERT v_place IS NOT NULL, 'AC2-H1: no place held';
    SELECT outcome INTO v_text FROM public.event_waitlist_place_offers
        WHERE place_id = v_place AND attendee_id = v_a;
    ASSERT v_text = 'Offered', 'AC2-H1: no place history row (D7)';
    ASSERT (SELECT closed_at FROM public.event_waitlist_places WHERE id = v_place) IS NULL,
        'AC2-H1: place closed while offered';
    SELECT array_agg(attendee_id ORDER BY queued_at, seq) INTO v_positions
        FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND status = 'Waiting';
    ASSERT v_positions = ARRAY[v_b, v_c, v_d], 'AC2-H1: queue behind A wrong';
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox
        WHERE entry_id = v_entry.id AND event_type = 'waitlist_offered'
          AND recipient_id = v_a AND published_at IS NULL) = 1,
        'AC2-H1: no single unpublished waitlist_offered for A';
    -- AC8-B2 (boundary): 1 Registered (H2) + 1 Offered (A) counts 2: the offer
    -- holds its place (D6), so nothing is free.
    ASSERT private.places_taken(v_event) = 2, 'AC2-H1: the offer does not hold its place';

    -- AC3-H1 (happy): the Coordinator chooses C; the automatic offer to A is revoked.
    PERFORM public.choose_waitlist_recipient(v_event, v_entry_c.id, v_k,
        c_t0 + interval '1 hour');
    SELECT * INTO v_entry FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND attendee_id = v_a;
    ASSERT v_entry.status = 'Waiting' AND v_entry.queued_at = c_t0,
        'AC3-H1: revoked holder must keep queued_at (D9)';
    ASSERT v_entry.offered_at IS NULL AND v_entry.expires_at IS NULL
        AND v_entry.place_id IS NULL, 'AC3-H1: revoked holder keeps offer fields';
    SELECT outcome INTO v_text FROM public.event_waitlist_place_offers
        WHERE place_id = v_place AND attendee_id = v_a;
    ASSERT v_text = 'Revoked', 'AC3-H1: history must say Revoked';
    SELECT * INTO v_entry_c FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND attendee_id = v_c;
    ASSERT v_entry_c.status = 'Offered'
        AND v_entry_c.expires_at = c_t0 + interval '73 hours'
        AND v_entry_c.place_id = v_place, 'AC3-H1: C not offered with a fresh window';
    SELECT outcome INTO v_text FROM public.event_waitlist_place_offers
        WHERE place_id = v_place AND attendee_id = v_c;
    ASSERT v_text = 'Offered', 'AC3-H1: C missing from the place history';
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox
        WHERE event_type = 'waitlist_offer_revoked' AND recipient_id = v_a) = 1,
        'AC3-H1: no revoke notice for A';
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox
        WHERE event_type = 'waitlist_offered' AND recipient_id = v_c) = 1,
        'AC3-H1: no offer notice for C';
    ASSERT private.places_taken(v_event) = 2, 'AC3-H1: the place is not held exactly once';

    -- AC4-B4..B5 (boundary): the timer expires only after the instant (D1),
    -- and AC9-H1: the expiry and the hand-over commit together.
    v_expired := v_entry_c.expires_at;
    PERFORM public.process_waitlist_timers(v_expired);
    SELECT status INTO v_text FROM public.event_waitlist_entries WHERE id = v_entry_c.id;
    ASSERT v_text = 'Offered', 'AC4-B4: the offer expired exactly at expires_at';
    PERFORM public.process_waitlist_timers(v_expired + interval '1 second');
    SELECT * INTO v_entry_c FROM public.event_waitlist_entries WHERE id = v_entry_c.id;
    ASSERT v_entry_c.status = 'Waiting' AND v_entry_c.queued_at = v_expired + interval '1 second',
        'AC4-B5: expired offeree not requeued to the back (D3)';
    ASSERT v_entry_c.offered_at IS NULL AND v_entry_c.expires_at IS NULL,
        'AC4-B5: requeued entry keeps offer fields';
    SELECT outcome INTO v_text FROM public.event_waitlist_place_offers
        WHERE place_id = v_place AND attendee_id = v_c;
    ASSERT v_text = 'Lapsed', 'AC4-B5: history must say Lapsed (D7)';
    SELECT * INTO v_entry_b FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND attendee_id = v_b;
    ASSERT v_entry_b.status = 'Offered' AND v_entry_b.place_id = v_place
        AND v_entry_b.expires_at = v_expired + interval '1 second' + interval '72 hours',
        'AC4-B5: B not offered with a fresh window';
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox
        WHERE event_type = 'waitlist_offer_expired' AND recipient_id = v_c) = 1,
        'AC4-B5: no single expired notice for C';
    ASSERT private.places_taken(v_event) = 2, 'AC9-H1: hand-over left the place unheld';

    -- AC4-X1 (cross-cutting): the timer is idempotent.
    PERFORM public.process_waitlist_timers(v_expired + interval '2 seconds');
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE id = v_entry_c.id)
        = 'Waiting', 'AC4-X1: requeued entry expired again';
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE id = v_entry_b.id)
        = 'Offered', 'AC4-X1: offered entry re-offered';
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox
        WHERE event_type = 'waitlist_offer_expired' AND recipient_id = v_c) = 1,
        'AC4-X1: duplicate expired notice';

    -- AC7-H1 (happy, database side): withdrawing with an offer passes it on.
    -- A was revoked on this place, not lapsed, so the place may come back (AC3-H2).
    PERFORM public.withdraw_from_waitlist(v_entry_b.id, v_b, c_t0 + interval '10 hours');
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE id = v_entry_b.id)
        = 'Withdrawn', 'AC7-H1: B not withdrawn';
    ASSERT (SELECT withdrawn_at FROM public.event_waitlist_entries WHERE id = v_entry_b.id)
        IS NOT NULL, 'AC7-H1: withdrawn_at not set';
    SELECT * INTO v_entry FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND attendee_id = v_a;
    ASSERT v_entry.status = 'Offered' AND v_entry.place_id = v_place,
        'AC7-H1: place not handed to the next eligible attendee';
    SELECT outcome INTO v_text FROM public.event_waitlist_place_offers
        WHERE place_id = v_place AND attendee_id = v_a;
    ASSERT v_text = 'Offered', 'AC7-H1: revoked holder not re-offered (D7)';
    ASSERT private.places_taken(v_event) = 2, 'AC7-H1: hand-over left the place unheld';

    -- AC4-H1 (happy, database side): accepting inside the window registers.
    v_entry := public.accept_waitlist_offer(v_entry.id, v_a, c_t0 + interval '34 hours');
    ASSERT v_entry.status = 'Accepted', 'AC4-H1: entry not Accepted';
    ASSERT (SELECT count(*) FROM public.event_registrations
        WHERE event_request_id = v_event AND attendee_id = v_a
          AND status = 'Registered') = 1, 'AC4-H1: no Registered row';
    ASSERT (SELECT outcome FROM public.event_waitlist_places WHERE id = v_place)
        = 'Accepted' AND (SELECT closed_at FROM public.event_waitlist_places
        WHERE id = v_place) IS NOT NULL, 'AC4-H1: place not closed as Accepted';
    ASSERT private.places_taken(v_event) = 2,
        'AC4-H1: accept changed the count (held -> registered)';

    -- H2's withdrawal opens a second place: D is offered (queued before the
    -- requeued C), and the Coordinator chooses C, revoking D (AC3/AC8-P3).
    -- C lapsed place 1, yet gets place 2: the history is per place (AC4-P3).
    v_reg2 := public.withdraw_registration(v_reg2.id, v_h[2], c_t0 + interval '20 hours');
    SELECT * INTO v_entry_d FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND attendee_id = v_d;
    ASSERT v_entry_d.status = 'Offered', 'AC9: D not offered the new place';
    v_place2 := v_entry_d.place_id;
    PERFORM public.choose_waitlist_recipient(v_event, v_entry_c.id, v_k,
        c_t0 + interval '20 hours');
    SELECT * INTO v_entry_d FROM public.event_waitlist_entries
        WHERE event_request_id = v_event AND attendee_id = v_d;
    ASSERT v_entry_d.status = 'Waiting' AND v_entry_d.queued_at = c_t0 + interval '3 seconds',
        'AC8-P3: revoked holder must keep queued_at';
    SELECT * INTO v_entry_c FROM public.event_waitlist_entries WHERE id = v_entry_c.id;
    ASSERT v_entry_c.status = 'Offered' AND v_entry_c.place_id = v_place2,
        'AC8-P3: C not offered place 2';
    ASSERT (SELECT outcome FROM public.event_waitlist_place_offers
        WHERE place_id = v_place AND attendee_id = v_c) = 'Lapsed',
        'AC4-P3: place 1 history changed';
    ASSERT private.places_taken(v_event) = 2,
        'AC8-P3: the hold after the revoke is wrong (0 free)';

    -- AC2-N2 (negative, D6): a direct registrant cannot take an offered place.
    BEGIN
        PERFORM public.register_for_event(v_event, v_f, c_t0 + interval '21 hours');
        RAISE EXCEPTION 'AC2-N2: direct registration took an offered place';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'event full', 'AC2-N2: wrong reason ' || SQLERRM;
    END;
    ASSERT (SELECT count(*) FROM public.event_registrations
        WHERE event_request_id = v_event AND attendee_id = v_f) = 0,
        'AC2-N2: refused registration left a row';

    -- AC8-N1 (negative, D6): a Coordinator's manual registration respects the hold.
    BEGIN
        PERFORM public.coordinator_register_attendee(v_event, v_k,
            'verify-scrum24-g@test.local');
        RAISE EXCEPTION 'AC8-N1: manual registration ignored the hold';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'event full', 'AC8-N1: wrong reason ' || SQLERRM;
    END;
    ASSERT (SELECT count(*) FROM public.event_registrations
        WHERE event_request_id = v_event AND attendee_id = v_g) = 0,
        'AC8-N1: refused manual registration left a row';

    -- AC2-P1 (partition): equal queued_at is broken by seq, never by list order.
    v_reg := public.register_for_event(v_eq, v_h[3], c_t0);
    INSERT INTO public.event_waitlist_entries
        (event_request_id, attendee_id, status, queued_at)
        VALUES (v_eq, v_c, 'Waiting', c_t0);          -- lower seq
    INSERT INTO public.event_waitlist_entries
        (event_request_id, attendee_id, status, queued_at)
        VALUES (v_eq, v_d, 'Waiting', c_t0);          -- higher seq, same time
    -- AC1-P1 (partition): the partial unique index allows one active entry.
    BEGIN
        INSERT INTO public.event_waitlist_entries
            (event_request_id, attendee_id, status, queued_at)
            VALUES (v_eq, v_c, 'Waiting', c_t0);
        RAISE EXCEPTION 'AC1-P1: a second Waiting entry was accepted';
    EXCEPTION WHEN unique_violation THEN NULL; END;
    v_reg := public.withdraw_registration(v_reg.id, v_h[3], c_t0);
    SELECT attendee_id INTO v_uuid FROM public.event_waitlist_entries
        WHERE event_request_id = v_eq AND status = 'Offered';
    ASSERT v_uuid = v_c, 'AC2-P1: seq did not break the tie';
    -- AC1-P2 (partition): an Offered entry is active too.
    BEGIN
        INSERT INTO public.event_waitlist_entries
            (event_request_id, attendee_id, status, queued_at)
            VALUES (v_eq, v_c, 'Waiting', c_t0);
        RAISE EXCEPTION 'AC1-P2: a Waiting entry was accepted while Offered';
    EXCEPTION WHEN unique_violation THEN NULL; END;

    -- AC4-P1 (partition, database side): a lone waitlister who lets the place
    -- lapse is not re-offered it; the place opens to registration (D7/D12).
    v_reg := public.register_for_event(v_small, v_h[4], c_t0);
    v_entry := public.join_waitlist(v_small, v_a, c_t0);
    PERFORM public.withdraw_registration(v_reg.id, v_h[4], c_t0 + interval '30 hours');
    SELECT * INTO v_entry FROM public.event_waitlist_entries
        WHERE event_request_id = v_small AND attendee_id = v_a;
    ASSERT v_entry.status = 'Offered', 'AC4-P1: lone waitlister not offered';
    v_place := v_entry.place_id;
    PERFORM public.process_waitlist_timers(v_entry.expires_at + interval '1 second');
    SELECT * INTO v_entry FROM public.event_waitlist_entries WHERE id = v_entry.id;
    ASSERT v_entry.status = 'Waiting', 'AC4-P1: lone waitlister not requeued (D3)';
    ASSERT (SELECT outcome FROM public.event_waitlist_places WHERE id = v_place)
        = 'Released', 'AC4-P1: place not released';
    ASSERT private.places_taken(v_small) = 0,
        'AC4-P1/AC8-P2: released place still counted (1 free expected)';
    ASSERT (SELECT count(*) FROM public.event_waitlist_place_offers
        WHERE place_id = v_place) = 1,
        'AC4-P1: the lapsed place was re-offered to the same attendee';

    -- AC2-N1 (negative): a place opens with nobody waiting.
    v_reg := public.register_for_event(v_empty, v_h[5], c_t0);
    PERFORM public.withdraw_registration(v_reg.id, v_h[5], c_t0);
    ASSERT private.places_taken(v_empty) = 0, 'AC2-N1: freed place still counted';
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_waitlist_entries
        WHERE event_request_id = v_empty), 'AC2-N1: an entry appeared';
    ASSERT NOT EXISTS (
        SELECT 1 FROM public.waitlist_notification_outbox o
        JOIN public.event_waitlist_entries e ON e.id = o.entry_id
        WHERE e.event_request_id = v_empty), 'AC2-N1: a notice appeared';

    -- AC2-N3 (negative): a failed promotion rolls back the whole withdrawal.
    -- AC5-N4 (negative): and writes no outbox notice.
    v_reg := public.register_for_event(v_fail, v_h[6], c_t0);
    v_entry := public.join_waitlist(v_fail, v_a, c_t0);
    CREATE FUNCTION pg_temp.scrum24_promotion_failure() RETURNS trigger
        LANGUAGE plpgsql AS $fn$ BEGIN
            RAISE EXCEPTION 'forced promotion failure';
        END $fn$;
    CREATE TRIGGER scrum24_force_promotion_failure
        BEFORE INSERT ON public.event_waitlist_place_offers
        FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum24_promotion_failure();
    BEGIN
        PERFORM public.withdraw_registration(v_reg.id, v_h[6], c_t0);
        RAISE EXCEPTION 'AC2-N3: withdrawal succeeded despite broken promotion';
    EXCEPTION
        WHEN OTHERS THEN
            ASSERT SQLERRM = 'forced promotion failure',
                'AC2-N3: wrong error: ' || SQLERRM;
    END;
    DROP TRIGGER scrum24_force_promotion_failure ON public.event_waitlist_place_offers;
    ASSERT (SELECT status FROM public.event_registrations WHERE id = v_reg.id)
        = 'Registered', 'AC2-N3: the withdrawal did not roll back';
    SELECT * INTO v_entry FROM public.event_waitlist_entries
        WHERE event_request_id = v_fail AND attendee_id = v_a;
    ASSERT v_entry.status = 'Waiting', 'AC2-N3: the entry changed';
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_waitlist_places
        WHERE event_request_id = v_fail), 'AC2-N3: a place row survived';
    ASSERT NOT EXISTS (
        SELECT 1 FROM public.waitlist_notification_outbox o
        JOIN public.event_waitlist_entries e ON e.id = o.entry_id
        WHERE e.event_request_id = v_fail), 'AC5-N4: a notice survived the rollback';

    -- AC10-B1..B2 (boundary) and AC10-N1 (negative): the list closes exactly at
    -- the cut-off, and the closing pass is idempotent (D11).
    v_reg := public.register_for_event(v_cutoff, v_h[1], c_t0);
    v_entry := public.join_waitlist(v_cutoff, v_a, c_t0);
    PERFORM public.process_waitlist_timers(c_cutoff - interval '1 second');
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE id = v_entry.id)
        = 'Waiting', 'AC10-B1: the entry closed before the cut-off';
    ASSERT NOT EXISTS (SELECT 1 FROM public.waitlist_notification_outbox o
        JOIN public.event_waitlist_entries e ON e.id = o.entry_id
        WHERE e.event_request_id = v_cutoff
          AND o.event_type = 'waitlist_closed'),
        'AC10-B1: a closing notice went out early';
    PERFORM public.process_waitlist_timers(c_cutoff);
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE id = v_entry.id)
        = 'Closed', 'AC10-B2: the entry did not close at the cut-off';
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox o
        JOIN public.event_waitlist_entries e ON e.id = o.entry_id
        WHERE e.event_request_id = v_cutoff
          AND o.event_type = 'waitlist_closed' AND o.recipient_id = v_a) = 1,
        'AC10-B2: no single waitlist_closed notice for A';
    PERFORM public.process_waitlist_timers(c_cutoff + interval '1 hour');
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox o
        JOIN public.event_waitlist_entries e ON e.id = o.entry_id
        WHERE e.event_request_id = v_cutoff
          AND o.event_type = 'waitlist_closed' AND o.recipient_id = v_a) = 1,
        'AC10-N1: the closing pass is not idempotent';
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE id = v_entry.id)
        = 'Closed', 'AC10-N1: a Closed entry changed';

    -- AC11-H1 (happy): a place freed after the cut-off opens to registration.
    PERFORM public.withdraw_registration(v_reg.id, v_h[1], c_cutoff + interval '1 day');
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE id = v_entry.id)
        = 'Closed', 'AC11-H1: a Closed entry became Offered';
    ASSERT private.places_taken(v_cutoff) = 0, 'AC11-H1: freed place still counted';
    v_reg := public.register_for_event(v_cutoff, v_f, c_cutoff + interval '1 day');
    ASSERT v_reg.status = 'Registered', 'AC11-H1: direct registration refused';

    -- AC12-H1 (happy): cancelling the event closes every entry, once each.
    v_reg := public.register_for_event(v_cancel, v_h[7], c_t0);
    v_reg2 := public.register_for_event(v_cancel, v_h[8], c_t0);
    v_entry := public.join_waitlist(v_cancel, v_a, c_t0);
    v_entry_b := public.join_waitlist(v_cancel, v_b, c_t0 + interval '1 second');
    PERFORM public.withdraw_registration(v_reg.id, v_h[7], c_t0);
    SELECT * INTO v_entry FROM public.event_waitlist_entries
        WHERE event_request_id = v_cancel AND attendee_id = v_a;
    ASSERT v_entry.status = 'Offered', 'AC12 setup: A not offered';
    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_cancel;
    SELECT status INTO v_text FROM public.event_waitlist_entries WHERE id = v_entry.id;
    ASSERT v_text = 'Closed', 'AC12-H1: the Offered entry did not close';
    SELECT status INTO v_text FROM public.event_waitlist_entries WHERE id = v_entry_b.id;
    ASSERT v_text = 'Closed', 'AC12-H1: the Waiting entry did not close';
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox o
        JOIN public.event_waitlist_entries e ON e.id = o.entry_id
        WHERE e.event_request_id = v_cancel
          AND o.event_type = 'waitlist_event_cancelled') = 2,
        'AC12-H1: not exactly one cancellation notice per entry';

    -- AC12-N1 (negative): a cancelled event never offers its places, and the
    -- timer leaves the Closed entries alone. The withdrawal half of the matrix
    -- row cannot go through 0062: withdraw_registration refuses a non-Confirmed
    -- event with 'withdrawal not permitted' (SCRUM-22 D1) -- flagged to the
    -- story owner; asserted here as the refusal it is today.
    BEGIN
        PERFORM public.withdraw_registration(v_reg2.id, v_h[8], c_t0 + interval '1 hour');
        RAISE EXCEPTION 'AC12-N1: withdrawal on a Cancelled event succeeded';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN
        ASSERT SQLERRM = 'withdrawal not permitted', 'AC12-N1: wrong reason ' || SQLERRM;
    END;
    PERFORM public.process_waitlist_timers(c_t0 + interval '2 hours');
    ASSERT (SELECT count(*) FROM public.event_waitlist_entries
        WHERE event_request_id = v_cancel AND status <> 'Closed') = 0,
        'AC12-N1: a Closed entry came back';
    ASSERT NOT EXISTS (SELECT 1 FROM public.event_waitlist_entries
        WHERE event_request_id = v_cancel AND status = 'Offered'),
        'AC12-N1: a cancelled event offered a place';
    -- H8 still holds the registration, so exactly one place is free.
    ASSERT private.places_taken(v_cancel) = 1, 'AC12-N1: places_remaining wrong';

    -- AC12-X1 (cross-cutting): the outbox tells only the story's own people.
    ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox o
        JOIN public.event_waitlist_entries e ON e.id = o.entry_id
        WHERE e.event_request_id = v_cancel
          AND o.recipient_id NOT IN (v_a, v_b)) = 0,
        'AC12-X1: a waitlist notice went to a registered attendee or the coordinator';

    -- AC1-X2 (cross-cutting): browser roles cannot reach the tables or the
    -- functions; service_role can execute the public API only.
    FOREACH v_text IN ARRAY ARRAY[
        'public.event_waitlist_entries', 'public.event_waitlist_places',
        'public.event_waitlist_place_offers', 'public.waitlist_notification_outbox'
    ] LOOP
        ASSERT NOT has_table_privilege('anon', v_text, 'SELECT'),
            'AC1-X2: anon can read ' || v_text;
        ASSERT NOT has_table_privilege('authenticated', v_text, 'INSERT'),
            'AC1-X2: authenticated can write ' || v_text;
        ASSERT has_table_privilege('service_role', v_text, 'SELECT'),
            'AC1-X2: service_role cannot read ' || v_text;
    END LOOP;
    FOREACH v_text IN ARRAY ARRAY[
        'public.join_waitlist(uuid,uuid,timestamptz)',
        'public.accept_waitlist_offer(uuid,uuid,timestamptz)',
        'public.withdraw_from_waitlist(uuid,uuid,timestamptz)',
        'public.choose_waitlist_recipient(uuid,uuid,text,timestamptz)',
        'public.process_waitlist_timers(timestamptz)'
    ] LOOP
        ASSERT NOT has_function_privilege('anon', v_text, 'EXECUTE'),
            'AC1-X2: anon can execute ' || v_text;
        ASSERT NOT has_function_privilege('authenticated', v_text, 'EXECUTE'),
            'AC1-X2: authenticated can execute ' || v_text;
        ASSERT has_function_privilege('service_role', v_text, 'EXECUTE'),
            'AC1-X2: service_role cannot execute ' || v_text;
    END LOOP;
    FOREACH v_text IN ARRAY ARRAY[
        'private.places_taken(uuid)',
        'private.offer_open_place(uuid,uuid,timestamptz)',
        'private.open_place(uuid,timestamptz)'
    ] LOOP
        ASSERT NOT has_function_privilege('service_role', v_text, 'EXECUTE'),
            'AC1-X2: service_role can execute the private helper ' || v_text;
    END LOOP;

    RAISE NOTICE 'ALL EVENT WAITLIST VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
