-- Run after 0055_venue_timing_change_reviews.sql (SCRUM-20 AC6). Every change is
-- rolled back. Borrows the oldest auth user as organiser, requester and staff.
-- The failure case adds a session-only trigger on the notification outbox, which
-- briefly locks that table until the ROLLBACK.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_venue_timing_change_reviews.sql
--
-- Times on day D (today + 10, Singapore); "0 / 45" means setup 0, turnaround 45.

BEGIN;

CREATE FUNCTION pg_temp.fail_outbox() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('verify.fail_outbox', true) = 'on' THEN
        RAISE EXCEPTION 'injected notification enqueue failure' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER verify_venue_timing_fail_outbox
    BEFORE INSERT ON public.arrangement_review_notification_outbox
    FOR EACH ROW EXECUTE FUNCTION pg_temp.fail_outbox();

DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
    v_today date := (now() AT TIME ZONE 'Asia/Singapore')::date;
    v_day date := (now() AT TIME ZONE 'Asia/Singapore')::date + 10;
    v_e1 uuid;
    v_e2 uuid;
    v_venue uuid;
    v_a uuid; v_b uuid; v_c uuid; v_x uuid; v_q uuid; v_r uuid; v_y uuid; v_z uuid;
    v_u1 uuid; v_u2 uuid; v_pending uuid;
    v_result jsonb;
    v_change uuid;
    v_reviews int;
    v_jobs int;
    v_changes int;
    v_sql text := 'INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, '
        'start_date, end_date, start_minute, end_minute, status, decided_by, decided_at) '
        'VALUES ($1, $2, $3, $4, $4, $5, $6, $7::public.booking_request_status, '
        'CASE WHEN $7 = ''pending'' THEN NULL ELSE $2 END, CASE WHEN $7 = ''pending'' THEN NULL ELSE now() END) '
        'RETURNING id';
BEGIN
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM20 AC6 event 1', 'Planning') RETURNING id INTO v_e1;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM20 AC6 event 2', 'Planning') RETURNING id INTO v_e2;
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM20 AC6 venue', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
        RETURNING id INTO v_venue;

    -- Venue 0 / 0. A 10:00-12:00 and B 12:30-14:00 (D, different events); C 16:00-17:00 (D);
    -- X 07:00-08:00 (D+1); Q 10:00-12:00 (D+3) and R 12:30-14:00 (D+4);
    -- Y 10:00-12:00 and Z 12:30-14:00 ended yesterday; U1 10:00-12:00 and U2 12:30-14:00 (D+5)
    -- point at events that do not exist; a pending 14:15-15:00 request on D.
    EXECUTE v_sql INTO v_a USING v_venue, v_user, v_e1, v_day, 600, 720, 'approved';
    EXECUTE v_sql INTO v_b USING v_venue, v_user, v_e2, v_day, 750, 840, 'approved';
    EXECUTE v_sql INTO v_c USING v_venue, v_user, v_e1, v_day, 960, 1020, 'approved';
    EXECUTE v_sql INTO v_x USING v_venue, v_user, v_e1, v_day + 1, 420, 480, 'approved';
    EXECUTE v_sql INTO v_q USING v_venue, v_user, v_e1, v_day + 3, 600, 720, 'approved';
    EXECUTE v_sql INTO v_r USING v_venue, v_user, v_e2, v_day + 4, 750, 840, 'approved';
    EXECUTE v_sql INTO v_y USING v_venue, v_user, v_e1, v_today - 1, 600, 720, 'approved';
    EXECUTE v_sql INTO v_z USING v_venue, v_user, v_e2, v_today - 1, 750, 840, 'approved';
    EXECUTE v_sql INTO v_u1 USING v_venue, v_user, gen_random_uuid(), v_day + 5, 600, 720, 'approved';
    EXECUTE v_sql INTO v_u2 USING v_venue, v_user, gen_random_uuid(), v_day + 5, 750, 840, 'approved';
    EXECUTE v_sql INTO v_pending USING v_venue, v_user, v_e1, v_day, 855, 900, 'pending';

    -- AC6-H1: raising turnaround to 45 flags both bookings of the new pair (A, B), saves the
    -- change, queues one notice per flag and leaves bookings unchanged. AC6-B2: Y and Z ended.
    -- AC6-P4: the pending request is ignored. AC6-P5: Q and R are on different days.
    v_result := public.update_venue_timing(v_venue, NULL, 45, v_user);
    v_change := (v_result->>'timing_change_id')::uuid;
    IF v_change IS NULL
       OR v_result->'flagged_booking_ids'
          <> to_jsonb(ARRAY(SELECT unnest(ARRAY[v_a, v_b]) ORDER BY 1))
       OR v_result->'unlinked_booking_ids'
          <> to_jsonb(ARRAY(SELECT unnest(ARRAY[v_u1, v_u2]) ORDER BY 1))
       OR (v_result->'venue'->>'turnaround_minutes')::int <> 45
       OR (v_result->'venue'->>'setup_minutes')::int <> 0 THEN
        RAISE EXCEPTION 'AC6-H1: wrong result: %', v_result;
    END IF;
    IF (SELECT count(*) FROM public.arrangement_reviews AS r
        WHERE r.trigger_id = v_change AND r.trigger_type = 'venue_timing_change'
          AND r.arrangement = 'venue_booking' AND r.changed_fields = '{turnaround_minutes}'
          AND r.cleared_at IS NULL
          AND (r.arrangement_id, r.event_request_id) IN ((v_a, v_e1), (v_b, v_e2))
          AND r.reason LIKE '%from 0 / 0 to 0 / 45 minutes; this booking now clashes%') <> 2
       OR (SELECT count(*) FROM public.arrangement_reviews WHERE trigger_id = v_change) <> 2 THEN
        RAISE EXCEPTION 'AC6-H1: flags not as expected';
    END IF;
    IF (SELECT count(*) FROM public.arrangement_review_notification_outbox AS o
        JOIN public.arrangement_reviews AS r ON r.id = o.review_id
        WHERE r.trigger_id = v_change AND o.payload->>'trigger_type' = 'venue_timing_change'
          AND NOT o.payload ? 'change_request_id') <> 2 THEN
        RAISE EXCEPTION 'AC6-H1: notices not queued';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.venue_timing_changes AS t
                   WHERE t.id = v_change AND t.venue_id = v_venue AND t.changed_by = v_user
                     AND (t.old_setup_minutes, t.old_turnaround_minutes,
                          t.new_setup_minutes, t.new_turnaround_minutes) = (0, 0, 0, 45)) THEN
        RAISE EXCEPTION 'AC6-H1: change record missing';
    END IF;
    IF (SELECT count(*) FROM public.venue_booking_requests
        WHERE venue_id = v_venue AND status = 'approved') <> 10
       OR (SELECT status FROM public.venue_booking_requests WHERE id = v_pending) <> 'pending' THEN
        RAISE EXCEPTION 'AC6-H1: a booking status changed';
    END IF;

    SELECT count(*) INTO v_reviews FROM public.arrangement_reviews;
    SELECT count(*) INTO v_jobs FROM public.arrangement_review_notification_outbox;
    SELECT count(*) INTO v_changes FROM public.venue_timing_changes;

    -- AC6-P1: an unchanged save (a replay of the same change, or no times at all) writes nothing.
    v_result := public.update_venue_timing(v_venue, 0, 45, v_user);
    IF v_result->'timing_change_id' <> 'null'::jsonb
       OR v_result->'flagged_booking_ids' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC6-P1: replay wrote something: %', v_result;
    END IF;
    PERFORM public.update_venue_timing(v_venue, NULL, NULL, v_user);
    IF (SELECT count(*) FROM public.arrangement_reviews) <> v_reviews
       OR (SELECT count(*) FROM public.arrangement_review_notification_outbox) <> v_jobs
       OR (SELECT count(*) FROM public.venue_timing_changes) <> v_changes THEN
        RAISE EXCEPTION 'AC6-P1: an unchanged save wrote rows';
    END IF;

    -- AC6-B1 / AC6-P3: raising setup to 30 flags X (07:00 start now pads to 06:30) and does not
    -- flag A and B again, as they already clashed.
    v_result := public.update_venue_timing(v_venue, 30, NULL, v_user);
    IF v_result->'flagged_booking_ids' <> to_jsonb(ARRAY[v_x])
       OR NOT EXISTS (SELECT 1 FROM public.arrangement_reviews AS r
                      WHERE r.trigger_id = (v_result->>'timing_change_id')::uuid
                        AND r.arrangement_id = v_x AND r.changed_fields = '{setup_minutes}'
                        AND r.reason LIKE '%padding that falls outside 07:00-24:00%') THEN
        RAISE EXCEPTION 'AC6-B1/P3: wrong flags: %', v_result;
    END IF;

    -- AC6-P2: lowering the times records the change but flags nothing.
    v_result := public.update_venue_timing(v_venue, 0, 0, v_user);
    IF v_result->'timing_change_id' = 'null'::jsonb
       OR v_result->'flagged_booking_ids' <> '[]'::jsonb THEN
        RAISE EXCEPTION 'AC6-P2: lowering flagged bookings: %', v_result;
    END IF;

    -- AC6-X1: if queuing a notice fails, the times, change record and flags all roll back.
    SELECT count(*) INTO v_reviews FROM public.arrangement_reviews;
    SELECT count(*) INTO v_jobs FROM public.arrangement_review_notification_outbox;
    SELECT count(*) INTO v_changes FROM public.venue_timing_changes;
    PERFORM set_config('verify.fail_outbox', 'on', true);
    BEGIN
        PERFORM public.update_venue_timing(v_venue, NULL, 60, v_user);
        RAISE EXCEPTION 'AC6-X1: the change succeeded despite the failure';
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        IF SQLERRM <> 'injected notification enqueue failure' THEN
            RAISE;
        END IF;
    END;
    PERFORM set_config('verify.fail_outbox', 'off', true);
    IF (SELECT (setup_minutes, turnaround_minutes) FROM public.venues WHERE id = v_venue) <> (0, 0)
       OR (SELECT count(*) FROM public.arrangement_reviews) <> v_reviews
       OR (SELECT count(*) FROM public.arrangement_review_notification_outbox) <> v_jobs
       OR (SELECT count(*) FROM public.venue_timing_changes) <> v_changes THEN
        RAISE EXCEPTION 'AC6-X1: a failed change left rows behind';
    END IF;

    -- AC6-N1: bad input is an error and changes nothing.
    BEGIN
        PERFORM public.update_venue_timing(gen_random_uuid(), 0, 45, v_user);
        RAISE EXCEPTION 'AC6-N1: unknown venue accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;
    BEGIN
        PERFORM public.update_venue_timing(v_venue, 20, 0, v_user);
        RAISE EXCEPTION 'AC6-N1: off-step setup accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        PERFORM public.update_venue_timing(v_venue, 0, 45, NULL);
        RAISE EXCEPTION 'AC6-N1: missing user accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;

    -- DB-1: only the server can change times through the function or read change records.
    IF has_function_privilege('anon', 'public.update_venue_timing(uuid, integer, integer, uuid)', 'EXECUTE')
       OR has_function_privilege('authenticated', 'public.update_venue_timing(uuid, integer, integer, uuid)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.update_venue_timing(uuid, integer, integer, uuid)', 'EXECUTE')
       OR has_table_privilege('anon', 'public.venue_timing_changes', 'SELECT')
       OR has_table_privilege('authenticated', 'public.venue_timing_changes', 'SELECT')
       OR has_table_privilege('service_role', 'public.venue_timing_changes', 'INSERT') THEN
        RAISE EXCEPTION 'DB-1: update_venue_timing or venue_timing_changes grants are wrong';
    END IF;

    RAISE NOTICE 'ALL SCRUM-20 AC6 TIMING CHANGE VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
