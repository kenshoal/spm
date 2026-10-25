-- Run after 0064_venue_block_booking_reviews.sql (SCRUM-63 AC1, AC2). Every change
-- is rolled back. Borrows the oldest auth user as organiser, requester and staff.
-- The failure case adds a session-only trigger on the notification outbox, which
-- briefly locks that table until the ROLLBACK.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_venue_block_booking_reviews.sql
--
-- Times are minutes after midnight (10:00 = 600). D is today + 10, Singapore.

BEGIN;

CREATE FUNCTION pg_temp.fail_outbox() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('verify.fail_outbox', true) = 'on' THEN
        RAISE EXCEPTION 'injected notification enqueue failure' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER verify_venue_block_fail_outbox
    BEFORE INSERT ON public.arrangement_review_notification_outbox
    FOR EACH ROW EXECUTE FUNCTION pg_temp.fail_outbox();

-- One booking request with the columns its status requires (0042's constraints).
CREATE FUNCTION pg_temp.add_booking(
    p_user uuid, p_venue uuid, p_event uuid, p_start date, p_end date,
    p_start_minute integer, p_end_minute integer, p_status text
) RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.venue_booking_requests (
        venue_id, requested_by, event_request_id, start_date, end_date,
        start_minute, end_minute, status,
        decided_by, decided_at, decision_reason, cancelled_by, cancelled_at)
    VALUES (
        p_venue, p_user, p_event, p_start, p_end, p_start_minute, p_end_minute,
        p_status::public.booking_request_status,
        CASE WHEN p_status IN ('approved', 'rejected') THEN p_user END,
        CASE WHEN p_status IN ('approved', 'rejected') THEN now() END,
        CASE WHEN p_status = 'rejected' THEN 'not suitable' END,
        CASE WHEN p_status = 'cancelled' THEN p_user END,
        CASE WHEN p_status = 'cancelled' THEN now() END)
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

DO $$
DECLARE
    v_user uuid := (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
    v_today date := (now() AT TIME ZONE 'Asia/Singapore')::date;
    v_day date := (now() AT TIME ZONE 'Asia/Singapore')::date + 10;
    v_e1 uuid; v_e2 uuid; v_e3 uuid;
    v_v1 uuid; v_v2 uuid;
    v_a uuid; v_b uuid; v_pending uuid; v_rejected uuid; v_cancelled uuid;
    v_other_venue uuid; v_cancelled_event uuid; v_orphan uuid;
    v_k uuid; v_y uuid; v_t uuid; v_m uuid;
    v_block public.venue_blocks;
    v_before jsonb;
    v_after jsonb;
    v_event_before jsonb;
    v_reviews int;
    v_jobs int;
    v_blocks int;
BEGIN
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM63 event 1', 'Planning') RETURNING id INTO v_e1;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM63 event 2', 'Planning') RETURNING id INTO v_e2;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_user, 'VERIFY SCRUM63 event 3', 'Planning') RETURNING id INTO v_e3;
    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_e3;
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM63 venue 1', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
        RETURNING id INTO v_v1;
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
            supported_layouts, operating_slots)
        VALUES ('VERIFY SCRUM63 venue 2', 'Test wing', 100, '{}', '{}',
            ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
        RETURNING id INTO v_v2;

    -- On day D at venue 1: A 09:00-12:00 (event 1) and B 13:00-15:00 (event 2) approved;
    -- a pending, a rejected and a cancelled 10:00-11:00 request; an approved 09:00-12:00
    -- booking at venue 2, one whose event is cancelled and one whose event does not exist.
    v_a := pg_temp.add_booking(v_user, v_v1, v_e1, v_day, v_day, 540, 720, 'approved');
    v_b := pg_temp.add_booking(v_user, v_v1, v_e2, v_day, v_day, 780, 900, 'approved');
    v_pending := pg_temp.add_booking(v_user, v_v1, v_e1, v_day, v_day, 600, 660, 'pending');
    v_rejected := pg_temp.add_booking(v_user, v_v1, v_e1, v_day, v_day, 600, 660, 'rejected');
    v_cancelled := pg_temp.add_booking(v_user, v_v1, v_e1, v_day, v_day, 600, 660, 'cancelled');
    v_other_venue := pg_temp.add_booking(v_user, v_v2, v_e1, v_day, v_day, 540, 720, 'approved');
    v_cancelled_event := pg_temp.add_booking(v_user, v_v1, v_e3, v_day, v_day, 540, 720, 'approved');
    v_orphan := pg_temp.add_booking(v_user, v_v1, gen_random_uuid(), v_day, v_day, 540, 720, 'approved');

    SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) INTO v_before FROM public.venue_booking_requests AS r;
    SELECT to_jsonb(e) INTO v_event_before FROM public.event_requests AS e WHERE e.id = v_e1;
    SELECT count(*) INTO v_reviews FROM public.arrangement_reviews;
    SELECT count(*) INTO v_jobs FROM public.arrangement_review_notification_outbox;

    -- AC1-H1, AC1-P1..P5, AC1-N3: blocking venue 1 on D 10:00-11:00 flags only A. B does not
    -- overlap; the pending, rejected and cancelled requests, the other venue's booking, the
    -- cancelled event's booking and the booking with no event are never flagged; the block
    -- is still saved.
    v_block := public.create_venue_block(v_v1, v_day, v_day, 600, 660, 'maintenance', 'VERIFY block 1', v_user);
    IF v_block.id IS NULL OR v_block.venue_id <> v_v1 OR v_block.start_minute <> 600
       OR v_block.end_minute <> 660 OR v_block.created_by <> v_user THEN
        RAISE EXCEPTION 'AC1-H1: wrong block returned: %', to_jsonb(v_block);
    END IF;
    IF (SELECT count(*) FROM public.arrangement_reviews AS r WHERE r.trigger_id = v_block.id) <> 1
       OR NOT EXISTS (SELECT 1 FROM public.arrangement_reviews AS r
                      WHERE r.trigger_id = v_block.id AND r.trigger_type = 'venue_block'
                        AND r.arrangement = 'venue_booking' AND r.arrangement_id = v_a
                        AND r.event_request_id = v_e1 AND r.changed_fields = '{}'
                        AND r.cleared_at IS NULL
                        AND r.reason = format(
                            'Venue VERIFY SCRUM63 venue 1 is blocked from %s to %s, 10:00 to 11:00; this booking needs a new venue.',
                            v_day, v_day)) THEN
        RAISE EXCEPTION 'AC1-H1 / AC1-P1..P5 / AC1-N3: flags not as expected';
    END IF;
    IF (SELECT count(*) FROM public.arrangement_reviews) <> v_reviews + 1 THEN
        RAISE EXCEPTION 'AC1-P1..P5: another review was written';
    END IF;

    -- AC2-H3: one notice is queued for the flag, with no change request.
    IF (SELECT count(*) FROM public.arrangement_review_notification_outbox AS o
        JOIN public.arrangement_reviews AS r ON r.id = o.review_id
        WHERE r.trigger_id = v_block.id AND o.payload->>'trigger_type' = 'venue_block'
          AND NOT o.payload ? 'change_request_id') <> 1
       OR (SELECT count(*) FROM public.arrangement_review_notification_outbox) <> v_jobs + 1 THEN
        RAISE EXCEPTION 'AC2-H3: notice not queued as expected';
    END IF;

    -- AC2-H1: flagging changes no booking and no event.
    SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) INTO v_after FROM public.venue_booking_requests AS r;
    IF v_after IS DISTINCT FROM v_before
       OR (SELECT to_jsonb(e) FROM public.event_requests AS e WHERE e.id = v_e1) IS DISTINCT FROM v_event_before THEN
        RAISE EXCEPTION 'AC2-H1: a booking or an event changed';
    END IF;

    -- AC1-B1..B3: a block ending where the booking starts, or starting where it ends, does
    -- not affect it; a block overlapping by one 15-minute step does. K is 09:00-12:00 on D+1.
    v_k := pg_temp.add_booking(v_user, v_v1, v_e1, v_day + 1, v_day + 1, 540, 720, 'approved');
    v_block := public.create_venue_block(v_v1, v_day + 1, v_day + 1, 480, 540, 'maintenance', 'VERIFY B1', v_user);
    IF EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE trigger_id = v_block.id) THEN
        RAISE EXCEPTION 'AC1-B1: a block ending where the booking starts flagged it';
    END IF;
    v_block := public.create_venue_block(v_v1, v_day + 1, v_day + 1, 720, 780, 'maintenance', 'VERIFY B3', v_user);
    IF EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE trigger_id = v_block.id) THEN
        RAISE EXCEPTION 'AC1-B3: a block starting where the booking ends flagged it';
    END IF;
    v_block := public.create_venue_block(v_v1, v_day + 1, v_day + 1, 705, 765, 'maintenance', 'VERIFY B2', v_user);
    IF (SELECT array_agg(arrangement_id) FROM public.arrangement_reviews WHERE trigger_id = v_block.id) IS DISTINCT FROM ARRAY[v_k] THEN
        RAISE EXCEPTION 'AC1-B2: a one-step overlap did not flag the booking';
    END IF;

    -- AC1-B4 / AC1-B5: a booking on today's date is still affected; one that ended
    -- yesterday is not.
    v_y := pg_temp.add_booking(v_user, v_v1, v_e1, v_today - 1, v_today - 1, 540, 720, 'approved');
    v_t := pg_temp.add_booking(v_user, v_v1, v_e1, v_today, v_today, 540, 720, 'approved');
    v_block := public.create_venue_block(v_v1, v_today - 1, v_today - 1, 600, 660, 'maintenance', 'VERIFY B5', v_user);
    IF EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE trigger_id = v_block.id) THEN
        RAISE EXCEPTION 'AC1-B5: a booking that ended yesterday was flagged';
    END IF;
    v_block := public.create_venue_block(v_v1, v_today, v_today, 600, 660, 'maintenance', 'VERIFY B4', v_user);
    IF (SELECT array_agg(arrangement_id) FROM public.arrangement_reviews WHERE trigger_id = v_block.id) IS DISTINCT FROM ARRAY[v_t] THEN
        RAISE EXCEPTION 'AC1-B4: the booking on today''s date was not flagged';
    END IF;

    -- AC1-B6: a multi-day booking is flagged when the block meets any one of its days.
    v_m := pg_temp.add_booking(v_user, v_v1, v_e2, v_day + 3, v_day + 5, 540, 720, 'approved');
    v_block := public.create_venue_block(v_v1, v_day + 6, v_day + 6, 600, 660, 'maintenance', 'VERIFY B6a', v_user);
    IF EXISTS (SELECT 1 FROM public.arrangement_reviews WHERE trigger_id = v_block.id) THEN
        RAISE EXCEPTION 'AC1-B6: the day after the booking flagged it';
    END IF;
    v_block := public.create_venue_block(v_v1, v_day + 5, v_day + 5, 600, 660, 'maintenance', 'VERIFY B6b', v_user);
    IF (SELECT array_agg(arrangement_id) FROM public.arrangement_reviews WHERE trigger_id = v_block.id) IS DISTINCT FROM ARRAY[v_m] THEN
        RAISE EXCEPTION 'AC1-B6: the last day of the booking did not flag it';
    END IF;

    -- AC1-H2: a block covering several days and both events flags every affected booking, once.
    v_block := public.create_venue_block(v_v1, v_day, v_day, 540, 900, 'maintenance', 'VERIFY H2', v_user);
    IF (SELECT array_agg(arrangement_id ORDER BY arrangement_id) FROM public.arrangement_reviews
        WHERE trigger_id = v_block.id) IS DISTINCT FROM (SELECT array_agg(x ORDER BY x) FROM unnest(ARRAY[v_a, v_b]) AS x) THEN
        RAISE EXCEPTION 'AC1-H2: not every affected booking was flagged once';
    END IF;

    -- AC1-N1: a block over nothing saves and flags nothing.
    SELECT count(*) INTO v_reviews FROM public.arrangement_reviews;
    v_block := public.create_venue_block(v_v1, v_day + 30, v_day + 30, 600, 660, 'maintenance', 'VERIFY N1', v_user);
    IF v_block.id IS NULL OR (SELECT count(*) FROM public.arrangement_reviews) <> v_reviews THEN
        RAISE EXCEPTION 'AC1-N1: a block over nothing wrote reviews or failed';
    END IF;

    -- AC1-N2: if queuing a notice fails, neither the block nor any flag is saved.
    SELECT count(*) INTO v_reviews FROM public.arrangement_reviews;
    SELECT count(*) INTO v_jobs FROM public.arrangement_review_notification_outbox;
    SELECT count(*) INTO v_blocks FROM public.venue_blocks;
    PERFORM set_config('verify.fail_outbox', 'on', true);
    BEGIN
        PERFORM public.create_venue_block(v_v1, v_day, v_day, 600, 660, 'maintenance', 'VERIFY N2', v_user);
        RAISE EXCEPTION 'AC1-N2: the block succeeded despite the failure';
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        IF SQLERRM <> 'injected notification enqueue failure' THEN
            RAISE;
        END IF;
    END;
    PERFORM set_config('verify.fail_outbox', 'off', true);
    IF (SELECT count(*) FROM public.arrangement_reviews) <> v_reviews
       OR (SELECT count(*) FROM public.arrangement_review_notification_outbox) <> v_jobs
       OR (SELECT count(*) FROM public.venue_blocks) <> v_blocks
       OR EXISTS (SELECT 1 FROM public.venue_blocks WHERE reason_detail = 'VERIFY N2') THEN
        RAISE EXCEPTION 'AC1-N2: a failed block left rows behind';
    END IF;

    -- Bad input is an error and changes nothing.
    BEGIN
        PERFORM public.create_venue_block(gen_random_uuid(), v_day, v_day, 600, 660, 'maintenance', NULL, v_user);
        RAISE EXCEPTION 'AC1-N2: unknown venue accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;

    -- AC1-X2: only the server can create blocks or write reviews; browser roles cannot.
    IF has_function_privilege('anon', 'public.create_venue_block(uuid, date, date, integer, integer, public.block_reason, text, uuid)', 'EXECUTE')
       OR has_function_privilege('authenticated', 'public.create_venue_block(uuid, date, date, integer, integer, public.block_reason, text, uuid)', 'EXECUTE')
       OR NOT has_function_privilege('service_role', 'public.create_venue_block(uuid, date, date, integer, integer, public.block_reason, text, uuid)', 'EXECUTE')
       OR has_table_privilege('anon', 'public.arrangement_reviews', 'INSERT')
       OR has_table_privilege('authenticated', 'public.arrangement_reviews', 'INSERT')
       OR has_table_privilege('service_role', 'public.arrangement_reviews', 'INSERT') THEN
        RAISE EXCEPTION 'AC1-X2: create_venue_block or arrangement_reviews grants are wrong';
    END IF;

    RAISE NOTICE 'ALL SCRUM-63 VENUE BLOCK BOOKING REVIEW VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
