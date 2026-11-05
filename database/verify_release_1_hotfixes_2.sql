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

-- 0086 (H4, SCRUM-40 AC9 and SCRUM-29 AC4): a Confirmed event with a recorded final end can be rescheduled
DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_who text := v_user::text;
    v_day date := (now() AT TIME ZONE 'Asia/Singapore')::date + 20;
    v_start timestamptz := ((now() AT TIME ZONE 'Asia/Singapore')::date + 20)::timestamp AT TIME ZONE 'Asia/Singapore' + interval '10 hours';
    v_event uuid; v_venue uuid; v_change uuid;
    v_row public.event_requests;
    v_chg public.event_change_requests;
BEGIN
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY H2 venue', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_venue;

    -- a Confirmed event with a booking and a recorded final end
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
            proposed_date_times, final_event_end_at)
        VALUES (v_user, 'VERIFY H2 confirmed', 'Planning', 20, ARRAY[v_start],
                v_start + interval '4 hours') RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_who, v_who);
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
            end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_event, v_day, v_day, 600, 840, 'approved', v_user, now());
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;

    -- AC9-H1 (happy): a Coordinator edit that moves the dates reopens the event and clears the end
    v_row := public.update_event_by_coordinator(v_event, v_who,
        (SELECT updated_at FROM public.event_requests WHERE id = v_event),
        jsonb_build_object('proposed_date_times', jsonb_build_array(v_start + interval '1 day')));
    ASSERT v_row.status = 'Planning', 'AC9-H1: a rescheduled Confirmed event must return to Planning';
    ASSERT v_row.final_event_end_at IS NULL, 'AC9-H1: the final end must be cleared';
    ASSERT v_row.proposed_date_times = ARRAY[v_start + interval '1 day'], 'AC9-H1: the new date should be saved';
    ASSERT EXISTS (SELECT 1 FROM public.event_request_status_history
                   WHERE event_request_id = v_event AND previous_status = 'Confirmed'
                     AND new_status = 'Planning' AND source = 'event_change.no_longer_confirmed'),
        'AC9-H1: the reopening must be in the status history as a system change';

    -- AC9-H2 (happy): the same with nothing to flag still reopens (the event stays consistent)
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
            proposed_date_times, final_event_end_at)
        VALUES (v_user, 'VERIFY H2 confirmed bare', 'Planning', 20, ARRAY[v_start],
                v_start + interval '4 hours') RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_who, v_who);
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;
    v_row := public.update_event_by_coordinator(v_event, v_who,
        (SELECT updated_at FROM public.event_requests WHERE id = v_event),
        jsonb_build_object('proposed_date_times', jsonb_build_array(v_start + interval '2 days')));
    ASSERT v_row.status = 'Planning' AND v_row.final_event_end_at IS NULL,
        'AC9-H2: with no arrangement to flag, the event must still reopen and lose its end';

    -- AC9-N1 (negative): an edit that does not move the dates leaves the end and the status alone
    UPDATE public.event_requests SET status = 'Planning', final_event_end_at = v_start + interval '2 days 4 hours'
        WHERE id = v_event;
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;
    v_row := public.update_event_by_coordinator(v_event, v_who,
        (SELECT updated_at FROM public.event_requests WHERE id = v_event), '{"purpose": "Same dates"}'::jsonb);
    ASSERT v_row.status = 'Confirmed' AND v_row.final_event_end_at IS NOT NULL,
        'AC9-N1: an ordinary edit must keep the status and the final end';

    -- AC8-N1 (negative): the final end cannot be changed directly once confirmed
    BEGIN
        UPDATE public.event_requests SET final_event_end_at = v_start WHERE id = v_event;
        RAISE EXCEPTION 'AC8-N1: a confirmed end was changed' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;

    -- AC8-N2 (negative): a Completed event's dates stay fixed while it has an end
    UPDATE public.event_requests SET status = 'Completed' WHERE id = v_event;
    BEGIN
        UPDATE public.event_requests SET proposed_date_times = ARRAY[v_start + interval '9 days'] WHERE id = v_event;
        RAISE EXCEPTION 'AC8-N2: a completed event was rescheduled' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;

    -- AC9-H3 (happy): the change-request route reschedules a Confirmed event with an end
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
            proposed_date_times, final_event_end_at)
        VALUES (v_user, 'VERIFY H2 change route', 'Planning', 20, ARRAY[v_start],
                v_start + interval '4 hours') RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_who, v_who);
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
            end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_event, v_day + 5, v_day + 5, 600, 840, 'approved', v_user, now());
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;
    v_chg := public.create_event_change_request(v_event, v_user, 'Move it a day',
        jsonb_build_object('proposed_date_times', jsonb_build_array(v_start + interval '1 day')));
    PERFORM public.approve_date_event_change_request(v_event, v_chg.id, v_who, NULL, NULL);
    v_row := (SELECT e FROM public.event_requests e WHERE e.id = v_event);
    ASSERT v_row.status = 'Planning' AND v_row.final_event_end_at IS NULL
        AND v_row.proposed_date_times = ARRAY[v_start + interval '1 day'],
        'AC9-H3: an approved date change must reopen the event, clear the end and save the date';
END $$;

-- 0087 (H2, SCRUM-24 AC2): a new offer is made only if its 72 hours end before registration closes
DO $$
DECLARE
    v_a uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_b uuid := (SELECT id FROM auth.users ORDER BY created_at, id OFFSET 1 LIMIT 1);
    v_c uuid := (SELECT id FROM auth.users ORDER BY created_at, id OFFSET 2 LIMIT 1);
    v_coord text := (SELECT id FROM auth.users ORDER BY created_at, id OFFSET 3 LIMIT 1)::text;
    v_event uuid; v_reg uuid; v_entry public.event_waitlist_entries;
    v_now timestamptz := now();
    v_status text;
    v_hours integer;
BEGIN
    -- Three cases: registration closes 71, 72 and 73 hours from now. The 72 hours must end strictly before it.
    FOREACH v_hours IN ARRAY ARRAY[71, 72, 73] LOOP
        INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
                proposed_date_times, registration_opens_at, registration_closes_at, registration_capacity)
            VALUES (v_a, 'VERIFY H2 waitlist ' || v_hours, 'Confirmed', 20,
                    ARRAY[v_now + interval '20 days'], v_now - interval '1 day',
                    v_now + make_interval(hours => v_hours), 1) RETURNING id INTO v_event;
        INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
            VALUES (v_event, v_coord, v_coord);
        PERFORM public.register_for_event(v_event, v_a, v_now);
        v_reg := (SELECT id FROM public.event_registrations WHERE event_request_id = v_event AND attendee_id = v_a);
        PERFORM public.join_waitlist(v_event, v_b, v_now);

        PERFORM public.withdraw_registration(v_reg, v_a, v_now);
        v_status := (SELECT status FROM public.event_waitlist_entries WHERE event_request_id = v_event AND attendee_id = v_b);

        IF v_hours <= 72 THEN
            -- AC2-B1, AC2-B2 (boundary): 71h and exactly 72h to close, the 72h window does not end before it
            ASSERT v_status = 'Waiting', 'AC2-B1/B2: no offer may reach registration close, hours=' || v_hours || ' got ' || v_status;
            ASSERT (SELECT count(*) FROM public.waitlist_notification_outbox o
                    JOIN public.event_waitlist_entries e ON e.id = o.entry_id
                    WHERE e.event_request_id = v_event AND o.event_type = 'waitlist_offered') = 0,
                'AC2-B1: no offer notice may be queued';
            ASSERT (SELECT outcome FROM public.event_waitlist_places WHERE event_request_id = v_event) = 'Released',
                'AC2-B1: the place goes to normal registration';
            -- AC3-N1 (negative): the Coordinator's choice cannot start a window past the close either
            BEGIN
                -- a place must be open for the override; reopen one by hand for the check
                INSERT INTO public.event_waitlist_places (event_request_id) VALUES (v_event);
                v_entry := public.choose_waitlist_recipient(v_event,
                    (SELECT id FROM public.event_waitlist_entries WHERE event_request_id = v_event AND attendee_id = v_b),
                    v_coord, v_now);
                RAISE EXCEPTION 'AC3-N1: an override ran past registration close' USING ERRCODE = 'P9901';
            EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
        ELSE
            -- AC2-B3 (boundary): 73h to close, the window ends before it, so the offer is made
            ASSERT v_status = 'Offered', 'AC2-B3: an offer inside the window must be made, got ' || v_status;
        END IF;
    END LOOP;
END $$;

-- 0088 (H1, SCRUM-45 AC2): a quantity cut below the peak reserved on any day is refused
DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_equip uuid; v_event uuid; v_req uuid;
    v_today date := (now() AT TIME ZONE 'Asia/Singapore')::date;
    v_row public.equipment;
BEGIN
    INSERT INTO public.equipment (type, total_owned_quantity, home_location, description)
        VALUES ('VERIFY H2 kit', 10, 'Store', 'x') RETURNING id INTO v_equip;
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance)
        VALUES (v_user, 'VERIFY H2 quantity', 'Planning', 20) RETURNING id INTO v_event;
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, event_name, event_date_times, recorded_by)
        VALUES (v_event, 'VERIFY H2 kit', 9, 'e', ARRAY[now()], v_user) RETURNING id INTO v_req;
    -- two overlapping reservations: 4 + 3 on the same two days (peak 7), and 2 on a later day alone
    INSERT INTO public.equipment_reservations (requirement_id, event_request_id, equipment_id, quantity, collection_date, return_date, created_by)
        VALUES (v_req, v_event, v_equip, 4, v_today + 10, v_today + 12, v_user),
               (v_req, v_event, v_equip, 3, v_today + 11, v_today + 13, v_user),
               (v_req, v_event, v_equip, 2, v_today + 20, v_today + 21, v_user);

    -- AC2-N1 (negative): below the peak (7) is refused and nothing changes
    BEGIN
        PERFORM public.update_equipment_quantity(v_equip, 6, v_user);
        RAISE EXCEPTION 'AC2-N1: a cut below the peak was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    ASSERT (SELECT total_owned_quantity FROM public.equipment WHERE id = v_equip) = 10,
        'AC2-N1: a refused cut changed the quantity';
    ASSERT (SELECT count(*) FROM public.equipment_quantity_history WHERE equipment_id = v_equip) = 0,
        'AC2-N1: a refused cut wrote history';
    -- AC2-B1 (boundary): exactly the peak is allowed
    v_row := public.update_equipment_quantity(v_equip, 7, v_user);
    ASSERT v_row.total_owned_quantity = 7, 'AC2-B1: a cut to exactly the peak should be saved';
    ASSERT (SELECT count(*) FROM public.equipment_quantity_history WHERE equipment_id = v_equip) = 1,
        'AC2-B1: the accepted cut should be in the history';
    -- AC2-B2 (boundary): one below the peak is refused
    BEGIN
        PERFORM public.update_equipment_quantity(v_equip, 6, v_user);
        RAISE EXCEPTION 'AC2-B2: one below the peak was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    -- AC2-P1 (partition): an increase is never refused
    v_row := public.update_equipment_quantity(v_equip, 12, v_user);
    ASSERT v_row.total_owned_quantity = 12, 'AC2-P1: an increase should be saved';
    -- AC2-P2 (partition): reservations that have already been returned do not hold the total up
    DELETE FROM public.equipment_reservations WHERE equipment_id = v_equip;
    INSERT INTO public.equipment_reservations (requirement_id, event_request_id, equipment_id, quantity, collection_date, return_date, created_by)
        VALUES (v_req, v_event, v_equip, 9, v_today - 20, v_today - 18, v_user);
    v_row := public.update_equipment_quantity(v_equip, 1, v_user);
    ASSERT v_row.total_owned_quantity = 1, 'AC2-P2: a returned reservation must not block a cut';
    -- AC2-B3 (boundary): two reservations that start the same day are each counted once
    INSERT INTO public.equipment_reservations (requirement_id, event_request_id, equipment_id, quantity, collection_date, return_date, created_by)
        VALUES (v_req, v_event, v_equip, 3, v_today + 30, v_today + 31, v_user),
               (v_req, v_event, v_equip, 3, v_today + 30, v_today + 32, v_user);
    v_row := public.update_equipment_quantity(v_equip, 6, v_user);
    ASSERT v_row.total_owned_quantity = 6, 'AC2-B3: 3 + 3 on the same day is a peak of 6, not 12';
    BEGIN
        PERFORM public.update_equipment_quantity(v_equip, 5, v_user);
        RAISE EXCEPTION 'AC2-B3: a cut below 3 + 3 was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    DELETE FROM public.equipment_reservations WHERE equipment_id = v_equip AND collection_date >= v_today;
    -- AC2-P3 (partition): zero stays allowed when nothing is reserved ahead
    v_row := public.update_equipment_quantity(v_equip, 0, v_user);
    ASSERT v_row.total_owned_quantity = 0, 'AC2-P3: zero should be allowed with nothing reserved ahead';
END $$;

-- 0089 (H5, SCRUM-38 AC2): filled_event is true only for the save that takes the event to full.
-- Needs the CI platform stub: it adds attendee accounts to auth.users (id, email) inside the transaction.
DO $$
DECLARE
    v_org uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_coord text := (SELECT id FROM auth.users ORDER BY created_at, id OFFSET 1 LIMIT 1)::text;
    u uuid[] := ARRAY[gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),
                      gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), gen_random_uuid()];
    v_now timestamptz := now();
    v_event uuid; v_venue uuid;
    v_row public.event_registrations;
    v_reg uuid;
    v_entry uuid;
    i integer;
BEGIN
    FOR i IN 1..7 LOOP
        INSERT INTO auth.users (id, email) VALUES (u[i], 'verify-h2-' || i || '@test.local');
    END LOOP;

    -- AC2-H1 (happy): capacity 3. The first two saves do not fill the event; the third does.
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
            proposed_date_times, registration_opens_at, registration_closes_at, registration_capacity)
        VALUES (v_org, 'VERIFY H2 full A', 'Confirmed', 20, ARRAY[v_now + interval '20 days'],
                v_now - interval '1 day', v_now + interval '10 days', 3) RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_coord, v_coord);
    v_row := public.register_for_event(v_event, u[1], v_now);
    ASSERT NOT v_row.filled_event, 'AC2-H1: the first of three places must not mark the event full';
    v_row := public.register_for_event(v_event, u[2], v_now);
    ASSERT NOT v_row.filled_event, 'AC2-H1: the second of three places must not mark the event full';
    v_row := public.register_for_event(v_event, u[3], v_now);
    ASSERT v_row.filled_event, 'AC2-H1: the third of three places must mark the event full';
    -- AC2-N1 (negative): a refused save marks nothing and stores nothing
    BEGIN
        PERFORM public.register_for_event(v_event, u[4], v_now);
        RAISE EXCEPTION 'AC2-N1: a registration into a full event was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    ASSERT (SELECT count(*) FROM public.event_registrations WHERE event_request_id = v_event AND filled_event) = 1,
        'AC2-N1: exactly one registration may carry the full mark';

    -- AC2-H2 (happy): a pending offer counts as occupied. Capacity 3 is raised to 5 while one place is offered.
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
            proposed_date_times, registration_opens_at, registration_closes_at, registration_capacity)
        VALUES (v_org, 'VERIFY H2 full B', 'Confirmed', 20, ARRAY[v_now + interval '20 days'],
                v_now - interval '1 day', v_now + interval '10 days', 3) RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_coord, v_coord);
    PERFORM public.register_for_event(v_event, u[1], v_now);
    PERFORM public.register_for_event(v_event, u[2], v_now);
    PERFORM public.register_for_event(v_event, u[3], v_now);
    PERFORM public.join_waitlist(v_event, u[4], v_now);
    v_reg := (SELECT id FROM public.event_registrations WHERE event_request_id = v_event AND attendee_id = u[1]);
    PERFORM public.withdraw_registration(v_reg, u[1], v_now);   -- u4 is offered the place
    ASSERT (SELECT status FROM public.event_waitlist_entries WHERE event_request_id = v_event AND attendee_id = u[4]) = 'Offered',
        'AC2-H2 setup: the freed place should be offered';
    PERFORM public.set_event_registration_settings(v_event, v_coord, v_now - interval '1 day',
        v_now + interval '10 days', 5, v_now);
    -- occupied is now u2, u3 and the offer to u4 = 3 of 5
    v_row := public.register_for_event(v_event, u[5], v_now);
    ASSERT NOT v_row.filled_event, 'AC2-H2: 3 occupied + 1 is 4 of 5, not full';
    v_row := public.register_for_event(v_event, u[6], v_now);
    ASSERT v_row.filled_event,
        'AC2-H2: 4 occupied (one of them an offer) + 1 is 5 of 5, full, although only 4 rows are Registered';

    -- AC2-N2 (negative): accepting the held offer does not mark the event full again
    v_entry := (SELECT id FROM public.event_waitlist_entries WHERE event_request_id = v_event AND attendee_id = u[4]);
    PERFORM public.accept_waitlist_offer(v_entry, u[4], v_now);
    ASSERT NOT (SELECT filled_event FROM public.event_registrations WHERE event_request_id = v_event AND attendee_id = u[4]),
        'AC2-N2: accepting an offer already held must not mark the event full';

    -- AC2-N3 (negative): a VIP added to an event that is already full is not "became full" again
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY H2 vip venue', 'Test wing', 50, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_venue;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
            end_date, start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_org, v_event, (v_now + interval '20 days')::date, (v_now + interval '20 days')::date,
                600, 720, 'approved', v_org, now());
    v_row := public.coordinator_register_attendee(v_event, v_coord, 'verify-h2-7@test.local');
    ASSERT NOT v_row.filled_event, 'AC2-N3: a VIP into an already full event must not announce full again';

    -- AC2-H3 (happy): a manual registration that takes the last place does mark it
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
            proposed_date_times, registration_opens_at, registration_closes_at, registration_capacity)
        VALUES (v_org, 'VERIFY H2 full C', 'Confirmed', 20, ARRAY[v_now + interval '20 days'],
                v_now - interval '1 day', v_now + interval '10 days', 2) RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_coord, v_coord);
    PERFORM public.register_for_event(v_event, u[1], v_now);
    v_row := public.coordinator_register_attendee(v_event, v_coord, 'verify-h2-2@test.local');
    ASSERT v_row.filled_event, 'AC2-H3: a manual registration taking the last place must mark the event full';
END $$;

-- 0090 (H8, SCRUM-32 AC2, AC6, AC7): who may request a venue booking, and when
DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_who text := v_user::text;
    v_today date := (now() AT TIME ZONE 'Asia/Singapore')::date;
    v_event uuid; v_venue uuid; v_venue2 uuid; v_old uuid; v_new uuid;
    v_row public.venue_booking_requests;
    v_status text;
BEGIN
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY H8 venue', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_venue;
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY H8 venue 2', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_venue2;
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance, accessibility_needs)
        VALUES (v_user, 'VERIFY H8 event', 'Planning', 20, 'Step-free access') RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_who, v_who);

    -- AC7-P1..P3 (partition): Approved, Planning and Safety Review accept a request
    FOREACH v_status IN ARRAY ARRAY['Approved', 'Planning', 'Safety Review'] LOOP
        UPDATE public.event_requests SET status = v_status WHERE id = v_event;
        v_row := public.create_event_venue_booking_request(jsonb_build_object(
            'id', gen_random_uuid(), 'venue_id', v_venue, 'event_request_id', v_event, 'requested_by', v_user,
            'start_date', v_today + 5, 'end_date', v_today + 5, 'start_minute', 600, 'end_minute', 720,
            'status', 'pending'), (SELECT updated_at FROM public.event_requests WHERE id = v_event));
        ASSERT v_row.status = 'pending', 'AC7-P: a request in ' || v_status || ' should be accepted';
    END LOOP;

    -- AC7-N1..N10 (negative): every other status is refused and stores nothing
    FOREACH v_status IN ARRAY ARRAY['Draft', 'Submitted', 'Under Review', 'Changes Requested', 'Confirmed',
            'Completed', 'Cancelled', 'Rejected', 'Withdrawn', 'Postponed'] LOOP
        UPDATE public.event_requests SET status = v_status WHERE id = v_event;
        BEGIN
            PERFORM public.create_event_venue_booking_request(jsonb_build_object(
                'id', gen_random_uuid(), 'venue_id', v_venue, 'event_request_id', v_event, 'requested_by', v_user,
                'start_date', v_today + 6, 'end_date', v_today + 6, 'start_minute', 600, 'end_minute', 720,
                'status', 'pending'), (SELECT updated_at FROM public.event_requests WHERE id = v_event));
            RAISE EXCEPTION 'AC7-N: a request in % was accepted', v_status USING ERRCODE = 'P9901';
        EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    END LOOP;
    ASSERT (SELECT count(*) FROM public.venue_booking_requests WHERE event_request_id = v_event
            AND start_date = v_today + 6) = 0, 'AC7-N: a refused request must store nothing';
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_event;

    -- AC6-B1 (boundary): today in Singapore is accepted
    v_row := public.create_event_venue_booking_request(jsonb_build_object(
        'id', gen_random_uuid(), 'venue_id', v_venue, 'event_request_id', v_event, 'requested_by', v_user,
        'start_date', v_today, 'end_date', v_today, 'start_minute', 600, 'end_minute', 720,
        'status', 'pending'), (SELECT updated_at FROM public.event_requests WHERE id = v_event));
    ASSERT v_row.start_date = v_today, 'AC6-B1: today should be accepted';
    -- AC6-B2 (boundary): yesterday is refused
    BEGIN
        PERFORM public.create_event_venue_booking_request(jsonb_build_object(
            'id', gen_random_uuid(), 'venue_id', v_venue, 'event_request_id', v_event, 'requested_by', v_user,
            'start_date', v_today - 1, 'end_date', v_today + 1, 'start_minute', 600, 'end_minute', 720,
            'status', 'pending'), (SELECT updated_at FROM public.event_requests WHERE id = v_event));
        RAISE EXCEPTION 'AC6-B2: a start date in the past was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;

    -- AC2-H1 (happy): the accessibility needs are copied; AC2-N1: a later edit does not rewrite them
    ASSERT v_row.accessibility_needs = 'Step-free access', 'AC2-H1: the accessibility snapshot is missing';
    UPDATE public.event_requests SET accessibility_needs = 'Hearing loop' WHERE id = v_event;
    ASSERT (SELECT accessibility_needs FROM public.venue_booking_requests WHERE id = v_row.id) = 'Step-free access',
        'AC2-N1: an event edit rewrote the snapshot';

    -- AC7-X1 (cross-cutting): a replacement still works for a Confirmed event and for a booking that
    -- has already started, which the rules for a new request would refuse
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date, end_date,
            start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_event, v_today - 1, v_today + 3, 600, 660, 'approved', v_user, now())
        RETURNING id INTO v_old;
    PERFORM public.create_venue_block(v_venue, v_today, v_today, 600, 660, 'maintenance', 'VERIFY H8', v_user);
    UPDATE public.event_requests SET status = 'Confirmed' WHERE id = v_event;
    v_new := gen_random_uuid();
    v_row := public.create_replacement_venue_booking_request(v_old, v_new, v_venue2, v_user,
        (SELECT updated_at FROM public.event_requests WHERE id = v_event));
    ASSERT v_row.id = v_new AND v_row.replaces_booking_id = v_old AND v_row.start_date = v_today - 1,
        'AC7-X1: a replacement should work for a Confirmed event and a booking that has begun';
    ASSERT v_row.accessibility_needs = 'Hearing loop', 'AC2-X1: a replacement request carries the accessibility snapshot too';
END $$;

-- 0091 (H9, SCRUM-64 AC1, SCRUM-29 AC5, SCRUM-35 AC1 and AC3): accessibility needs flag venue bookings
DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at, id LIMIT 1);
    v_who text := v_user::text;
    v_today date := (now() AT TIME ZONE 'Asia/Singapore')::date;
    v_start timestamptz := ((now() AT TIME ZONE 'Asia/Singapore')::date + 40)::timestamp AT TIME ZONE 'Asia/Singapore' + interval '10 hours';
    v_event uuid; v_venue uuid; v_booking uuid; v_equip uuid; v_req uuid;
    v_row public.event_requests;
    v_chg public.event_change_requests;
    v_count integer;
BEGIN
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY H9 venue', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_venue;
    INSERT INTO public.event_requests (organiser_id, event_name, status, expected_attendance,
            proposed_date_times, accessibility_needs)
        VALUES (v_user, 'VERIFY H9 event', 'Planning', 20, ARRAY[v_start], 'Step-free access')
        RETURNING id INTO v_event;
    INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
        VALUES (v_event, v_who, v_who);
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date, end_date,
            start_minute, end_minute, status, decided_by, decided_at)
        VALUES (v_venue, v_user, v_event, v_today + 40, v_today + 40, 600, 720, 'approved', v_user, now())
        RETURNING id INTO v_booking;
    -- an equipment reservation, which an accessibility change must NOT flag
    INSERT INTO public.equipment (type, total_owned_quantity, home_location, description)
        VALUES ('VERIFY H9 kit', 5, 'Store', 'x') RETURNING id INTO v_equip;
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, event_name, event_date_times, recorded_by)
        VALUES (v_event, 'VERIFY H9 kit', 2, 'e', ARRAY[v_start], v_user) RETURNING id INTO v_req;
    INSERT INTO public.equipment_reservations (requirement_id, event_request_id, equipment_id, quantity,
            collection_date, return_date, created_by)
        VALUES (v_req, v_event, v_equip, 2, v_today + 39, v_today + 40, v_user);

    -- AC1-N1 (negative): an ordinary edit, and a save with the same accessibility text, flag nothing
    v_row := public.update_event_by_coordinator(v_event, v_who,
        (SELECT updated_at FROM public.event_requests WHERE id = v_event),
        '{"purpose": "A new purpose", "accessibility_needs": "Step-free access"}'::jsonb);
    ASSERT (SELECT count(*) FROM public.arrangement_reviews WHERE event_request_id = v_event) = 0,
        'AC1-N1: an unchanged accessibility value or an ordinary edit must not flag';

    -- AC1-H1 (happy): the Coordinator edit flags the approved booking once, naming the field
    v_row := public.update_event_by_coordinator(v_event, v_who,
        (SELECT updated_at FROM public.event_requests WHERE id = v_event),
        '{"accessibility_needs": "Step-free access and a hearing loop"}'::jsonb);
    ASSERT (SELECT count(*) FROM public.arrangement_reviews
            WHERE event_request_id = v_event AND arrangement = 'venue_booking' AND arrangement_id = v_booking
              AND 'accessibility_needs' = ANY(changed_fields) AND cleared_at IS NULL) = 1,
        'AC1-H1: the booking must be flagged once for the accessibility change';
    ASSERT (SELECT count(*) FROM public.arrangement_reviews
            WHERE event_request_id = v_event AND arrangement = 'equipment_reservation') = 0,
        'AC1-N2: an accessibility change must not flag equipment reservations';

    -- AC1-H2 (happy): a direct single-column update flags too, so the trigger must watch the column itself
    DELETE FROM public.arrangement_review_notification_outbox
        WHERE review_id IN (SELECT id FROM public.arrangement_reviews WHERE event_request_id = v_event);
    DELETE FROM public.arrangement_reviews WHERE event_request_id = v_event;
    UPDATE public.event_requests SET accessibility_needs = 'Step-free access and a ramp' WHERE id = v_event;
    ASSERT (SELECT count(*) FROM public.arrangement_reviews
            WHERE event_request_id = v_event AND arrangement = 'venue_booking' AND arrangement_id = v_booking
              AND 'accessibility_needs' = ANY(changed_fields)) = 1,
        'AC1-H2: a direct update of the column must flag the booking once';

    -- AC1-P1 (partition): a blank-to-blank or whitespace-only change is no change
    DELETE FROM public.arrangement_review_notification_outbox
        WHERE review_id IN (SELECT id FROM public.arrangement_reviews WHERE event_request_id = v_event);
    DELETE FROM public.arrangement_reviews WHERE event_request_id = v_event;
    UPDATE public.event_requests SET accessibility_needs = NULL WHERE id = v_event;
    DELETE FROM public.arrangement_review_notification_outbox
        WHERE review_id IN (SELECT id FROM public.arrangement_reviews WHERE event_request_id = v_event);
    DELETE FROM public.arrangement_reviews WHERE event_request_id = v_event;
    UPDATE public.event_requests SET accessibility_needs = '   ' WHERE id = v_event;
    ASSERT (SELECT count(*) FROM public.arrangement_reviews WHERE event_request_id = v_event) = 0,
        'AC1-P1: empty and whitespace-only accessibility text are the same, so nothing is flagged';

    -- AC3-H1 (happy): the change-request route applies the value and flags the booking once
    UPDATE public.event_requests SET accessibility_needs = 'Step-free access' WHERE id = v_event;
    DELETE FROM public.arrangement_review_notification_outbox
        WHERE review_id IN (SELECT id FROM public.arrangement_reviews WHERE event_request_id = v_event);
    DELETE FROM public.arrangement_reviews WHERE event_request_id = v_event;
    v_chg := public.create_event_change_request(v_event, v_user, 'We need a quiet room as well',
        '{"accessibility_needs": "Step-free access and a quiet room"}'::jsonb);
    PERFORM public.approve_non_date_event_change_request(v_event, v_chg.id, v_who, NULL);
    ASSERT (SELECT accessibility_needs FROM public.event_requests WHERE id = v_event) = 'Step-free access and a quiet room',
        'AC3-H1: the approved accessibility value must be saved';
    ASSERT (SELECT count(*) FROM public.arrangement_reviews
            WHERE event_request_id = v_event AND arrangement = 'venue_booking' AND arrangement_id = v_booking
              AND 'accessibility_needs' = ANY(changed_fields)) = 1,
        'AC3-H1: the booking must be flagged once by the approval';

    -- AC3-N1 (negative): a proposal that repeats the stored accessibility text is refused as no change
    BEGIN
        PERFORM public.create_event_change_request(v_event, v_user, 'Same again',
            '{"accessibility_needs": "Step-free access and a quiet room"}'::jsonb);
        RAISE EXCEPTION 'AC3-N1: an unchanged accessibility proposal was accepted' USING ERRCODE = 'P9901';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;

    -- AC3-H2 (happy): the date route carries an accessibility value along with the new date
    DELETE FROM public.arrangement_review_notification_outbox
        WHERE review_id IN (SELECT id FROM public.arrangement_reviews WHERE event_request_id = v_event);
    DELETE FROM public.arrangement_reviews WHERE event_request_id = v_event;
    v_chg := public.create_event_change_request(v_event, v_user, 'Move a day and add a signer',
        jsonb_build_object('proposed_date_times', jsonb_build_array(v_start + interval '1 day'),
                           'accessibility_needs', 'Step-free access and a sign-language interpreter'));
    PERFORM public.approve_date_event_change_request(v_event, v_chg.id, v_who, NULL, NULL);
    ASSERT (SELECT accessibility_needs FROM public.event_requests WHERE id = v_event) = 'Step-free access and a sign-language interpreter',
        'AC3-H2: the accessibility value must be saved with the date change';
END $$;

-- 0092 (H12, SCRUM-30 AC1, AC2, AC6): a venue's daily operating hours
DO $$
DECLARE
    v_id uuid;
    v_hours integer[];
BEGIN
    -- AC1-P1 (partition): a venue created without hours operates the whole day
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY H12 venue', 'Test wing', 100, '{}', '{theatre}', '{theatre}', '{AM,PM,NIGHT}')
        RETURNING id INTO v_id;
    ASSERT (SELECT operating_start_minute FROM public.venues WHERE id = v_id) = 420
       AND (SELECT operating_end_minute FROM public.venues WHERE id = v_id) = 1440,
        'AC1-P1: the default hours should be 07:00 to 24:00';

    -- AC1-H1, AC1-B1, AC1-B2 (happy and boundary): valid ranges are accepted, including a single quarter hour at either edge
    FOREACH v_hours SLICE 1 IN ARRAY ARRAY[ARRAY[540, 1080], ARRAY[420, 435], ARRAY[1425, 1440], ARRAY[420, 1440]] LOOP
        UPDATE public.venues SET operating_start_minute = v_hours[1], operating_end_minute = v_hours[2] WHERE id = v_id;
        ASSERT (SELECT operating_start_minute FROM public.venues WHERE id = v_id) = v_hours[1],
            'AC1-H1: hours ' || v_hours[1] || '-' || v_hours[2] || ' should be accepted';
    END LOOP;

    -- AC6-N1..N6 (negative): an invalid range is refused and the stored hours do not change
    UPDATE public.venues SET operating_start_minute = 540, operating_end_minute = 1080 WHERE id = v_id;
    FOREACH v_hours SLICE 1 IN ARRAY ARRAY[ARRAY[405, 1080], ARRAY[540, 1455], ARRAY[545, 1080], ARRAY[540, 1085],
            ARRAY[600, 600], ARRAY[900, 600]] LOOP
        BEGIN
            UPDATE public.venues SET operating_start_minute = v_hours[1], operating_end_minute = v_hours[2] WHERE id = v_id;
            RAISE EXCEPTION 'AC6-N: hours %-% were accepted', v_hours[1], v_hours[2] USING ERRCODE = 'P9901';
        EXCEPTION WHEN check_violation THEN NULL; END;
    END LOOP;
    ASSERT (SELECT operating_start_minute FROM public.venues WHERE id = v_id) = 540
       AND (SELECT operating_end_minute FROM public.venues WHERE id = v_id) = 1080,
        'AC6-N: a refused range must leave the stored hours alone';

    -- AC6-N7 (negative): a venue cannot be created with an invalid range either
    BEGIN
        INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
                supported_layouts, operating_slots, operating_start_minute, operating_end_minute)
            VALUES ('VERIFY H12 bad venue', 'Test wing', 10, '{}', '{theatre}', '{theatre}', '{AM}', 1000, 900);
        RAISE EXCEPTION 'AC6-N7: an inverted range was accepted on insert' USING ERRCODE = 'P9901';
    EXCEPTION WHEN check_violation THEN NULL; END;
END $$;

DO $$ BEGIN RAISE NOTICE 'ALL HOTFIX 2 VERIFICATIONS PASSED'; END $$;

ROLLBACK;
