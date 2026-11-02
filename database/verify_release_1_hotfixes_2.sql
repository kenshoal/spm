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

DO $$ BEGIN RAISE NOTICE 'ALL HOTFIX 2 VERIFICATIONS PASSED'; END $$;

ROLLBACK;
