-- SCRUM-64 AC1/AC2: real accepted event UPDATE -> durable arrangement review.
-- Disposable PG only, after read schema0029 and domain migrations including
-- SCRUM-13's requirement-linked reservations. No production helper is mocked.
-- Run with psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_flags.sql.
-- Date anchor is the fixed transaction instant in Asia/Singapore; all fixtures
-- roll back. Notification production/delivery and shared readiness are excluded.
BEGIN;

CREATE TEMP SEQUENCE scrum64_flag_attempts;
CREATE FUNCTION pg_temp.scrum64_fail_second_flag() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.event_request_id::text = current_setting('scrum64.atomic_event', true) THEN
        IF nextval('pg_temp.scrum64_flag_attempts') = 2 THEN
            RAISE EXCEPTION 'SCRUM64 injected second flag failure' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER scrum64_test_fail_second_flag BEFORE INSERT ON public.arrangement_reviews
    FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum64_fail_second_flag();

CREATE FUNCTION pg_temp.scrum64_protected_state() RETURNS jsonb
LANGUAGE sql STABLE AS $$
SELECT jsonb_build_object(
    'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.venue_booking_requests r),
    'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_reservations r),
    'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_requirements r),
    'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment r),
    'history',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_status_history r)
);
$$;

DO $$
DECLARE
    v_today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
    v_date timestamptz;
    v_actor uuid;
    v_event uuid;
    v_other uuid;
    v_atomic uuid;
    v_ineligible uuid[] := '{}';
    v_ineligible_event uuid;
    v_status text;
    v_venue uuid;
    v_equipment uuid;
    v_requirement uuid;
    v_booking uuid;
    v_reservation uuid;
    v_past_booking uuid;
    v_today_booking uuid;
    v_future_booking uuid;
    v_past_reservation uuid;
    v_today_reservation uuid;
    v_future_reservation uuid;
    v_pending uuid;
    v_rejected uuid;
    v_offset integer;
    v_before jsonb;
    v_flags jsonb;
    v_notices jsonb;
    v_outbox jsonb;
    v_event_before jsonb;
    v_old_ids uuid[];
    v_trigger uuid;
    v_first_trigger uuid;
    v_count integer;
    v_message text;
    v_writer record;
    v_writers integer := 0;
BEGIN
    SELECT id INTO v_actor FROM auth.users ORDER BY id LIMIT 1;
    ASSERT v_actor IS NOT NULL, 'fixture: disposable auth identity required';
    v_date := ((v_today+3) + TIME '09:00') AT TIME ZONE 'Asia/Singapore';
    INSERT INTO public.event_requests
        (organiser_id,event_name,status,proposed_date_times,expected_attendance,
         venue_requirements,equipment_requirements)
    VALUES (v_actor,'VERIFY SCRUM64 flags main','Planning',ARRAY[v_date],25,
            'Seminar room','Microphone') RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id,event_name,status,expected_attendance)
    VALUES (v_actor,'VERIFY SCRUM64 flags other','Planning',25) RETURNING id INTO v_other;
    INSERT INTO public.event_requests (organiser_id,event_name,status,expected_attendance)
    VALUES (v_actor,'VERIFY SCRUM64 flags atomic','Planning',25) RETURNING id INTO v_atomic;
    FOREACH v_status IN ARRAY ARRAY['Draft','Completed','Cancelled','Rejected'] LOOP
        INSERT INTO public.event_requests (organiser_id,event_name,status,expected_attendance)
        VALUES (v_actor,'VERIFY SCRUM64 ineligible '||v_status,v_status,25)
        RETURNING id INTO v_ineligible_event;
        v_ineligible := array_append(v_ineligible,v_ineligible_event);
    END LOOP;
    INSERT INTO public.venues
        (name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
    VALUES ('VERIFY SCRUM64 venue','Test wing',100,'{}','{}',
            ARRAY['theatre']::public.room_layout[],ARRAY['AM']::public.booking_slot[])
    RETURNING id INTO v_venue;
    INSERT INTO public.equipment (type,total_owned_quantity,home_location,created_by)
    VALUES ('VERIFY SCRUM64 Microphone',100,'Test store',v_actor) RETURNING id INTO v_equipment;
    INSERT INTO public.equipment_requirements
        (event_request_id,equipment_type,quantity,recorded_by)
    VALUES (v_event,'VERIFY SCRUM64 Microphone',100,v_actor) RETURNING id INTO v_requirement;

    FOR v_offset IN -1..1 LOOP
        INSERT INTO public.venue_booking_requests
            (venue_id,requested_by,event_request_id,start_date,end_date,slots,
             status,decided_by,decided_at)
        VALUES (v_venue,v_actor,v_event,v_today+v_offset-2,v_today+v_offset,
                ARRAY['AM']::public.booking_slot[],'approved',v_actor,transaction_timestamp())
        RETURNING id INTO v_booking;
        INSERT INTO public.equipment_reservations
            (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
        VALUES (v_equipment,v_requirement,v_event,1,v_today+v_offset-2,v_today+v_offset,v_actor)
        RETURNING id INTO v_reservation;
        IF v_offset=-1 THEN v_past_booking:=v_booking; v_past_reservation:=v_reservation;
        ELSIF v_offset=0 THEN v_today_booking:=v_booking; v_today_reservation:=v_reservation;
        ELSE v_future_booking:=v_booking; v_future_reservation:=v_reservation; END IF;
    END LOOP;
    INSERT INTO public.venue_booking_requests
        (venue_id,requested_by,event_request_id,start_date,end_date,slots,status)
    VALUES (v_venue,v_actor,v_event,v_today,v_today+1,ARRAY['AM']::public.booking_slot[],'pending')
    RETURNING id INTO v_pending;
    INSERT INTO public.venue_booking_requests
        (venue_id,requested_by,event_request_id,start_date,end_date,slots,status,
         decided_by,decided_at,decision_reason)
    VALUES (v_venue,v_actor,v_event,v_today,v_today+1,ARRAY['AM']::public.booking_slot[],
            'rejected',v_actor,transaction_timestamp(),'Fixture rejection') RETURNING id INTO v_rejected;

    -- These other events all have eligible-looking arrangements, so excluding
    -- their rows is a non-vacuous event/status rule, not an empty-fixture pass.
    FOREACH v_ineligible_event IN ARRAY array_cat(ARRAY[v_other,v_atomic],v_ineligible) LOOP
        INSERT INTO public.venue_booking_requests
            (venue_id,requested_by,event_request_id,start_date,end_date,slots,
             status,decided_by,decided_at)
        VALUES (v_venue,v_actor,v_ineligible_event,v_today-1,v_today+1,
                ARRAY['AM']::public.booking_slot[],'approved',v_actor,transaction_timestamp());
        INSERT INTO public.equipment_requirements
            (event_request_id,equipment_type,quantity,recorded_by)
        VALUES (v_ineligible_event,'VERIFY SCRUM64 Microphone',10,v_actor)
        RETURNING id INTO v_requirement;
        INSERT INTO public.equipment_reservations
            (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
        VALUES (v_equipment,v_requirement,v_ineligible_event,1,v_today-1,v_today+1,v_actor);
    END LOOP;
    v_before := pg_temp.scrum64_protected_state();

    -- AC1-H1 (happy): one accepted reschedule raises both domains under one real trigger.
    SET LOCAL ROLE service_role;
    UPDATE public.event_requests SET proposed_date_times=ARRAY[v_date+INTERVAL '1 day']
        WHERE id=v_event;
    RESET ROLE;
    SELECT count(*) INTO v_count FROM public.arrangement_reviews WHERE event_request_id=v_event;
    ASSERT v_count=4, 'AC1-H1: accepted date change must create four eligible arrangement flags';
    ASSERT (SELECT count(DISTINCT trigger_id)=1 FROM public.arrangement_reviews WHERE event_request_id=v_event),
        'AC1-H1: one accepted update must share one trigger UUID';
    SELECT trigger_id INTO v_first_trigger FROM public.arrangement_reviews WHERE event_request_id=v_event LIMIT 1;
    ASSERT (SELECT bool_and(trigger_type='event_change' AND changed_fields=ARRAY['proposed_date_times']
                AND strpos(reason,((v_date AT TIME ZONE 'Asia/Singapore')::date)::text)>0
                AND strpos(reason,(((v_date+INTERVAL '1 day') AT TIME ZONE 'Asia/Singapore')::date)::text)>0
                AND btrim(reason)<>'' AND raised_at IS NOT NULL AND cleared_at IS NULL AND cleared_by IS NULL)
            FROM public.arrangement_reviews WHERE event_request_id=v_event), 'AC1-H1: actual change evidence incomplete';
    ASSERT (SELECT count(*)=2 FROM public.arrangement_reviews WHERE event_request_id=v_event
            AND arrangement='venue_booking' AND arrangement_id=ANY(ARRAY[v_today_booking,v_future_booking])),
        'AC1-H1: wrong venue targets';
    ASSERT (SELECT count(*)=2 FROM public.arrangement_reviews WHERE event_request_id=v_event
            AND arrangement='equipment_reservation' AND arrangement_id=ANY(ARRAY[v_today_reservation,v_future_reservation])),
        'AC1-H1: wrong reservation targets';
    ASSERT NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=v_other),
        'AC1-H1: other event received flags';

    -- AC1-H1 (happy): the native service update works without exposing its private audit writer as a callable RPC.
    FOR v_writer IN
        SELECT p.oid,p.prosecdef,p.proconfig,n.nspname
        FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
        JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE t.tgrelid='public.event_requests'::regclass AND NOT t.tgisinternal
          AND (t.tgtype::integer & 16)=16 AND (t.tgtype::integer & 2)=0
          AND (cardinality(t.tgattr::smallint[])=0 OR t.tgattr::smallint[] && ARRAY(
              SELECT attnum FROM pg_attribute WHERE attrelid=t.tgrelid
              AND attname IN('proposed_date_times','expected_attendance','venue_requirements','equipment_requirements')))
    LOOP
        v_writers:=v_writers+1;
        ASSERT v_writer.prosecdef AND v_writer.nspname='private', 'AC1-H1: native audit writer is not private SECURITY DEFINER';
        ASSERT EXISTS(SELECT 1 FROM unnest(v_writer.proconfig) c WHERE c IN('search_path=','search_path=""')),
            'AC1-H1: audit writer search_path is not empty';
        ASSERT NOT has_function_privilege('service_role',v_writer.oid,'EXECUTE')
            AND NOT has_function_privilege('anon',v_writer.oid,'EXECUTE')
            AND NOT has_function_privilege('authenticated',v_writer.oid,'EXECUTE'),
            'AC1-H1: audit writer is directly executable by a caller role';
    END LOOP;
    ASSERT v_writers>0, 'AC1-H1: no protected native detail-update writer discovered';

    -- AC1-B1 (boundary): arrangements ending yesterday remain historical, not current review work.
    ASSERT NOT EXISTS(SELECT 1 FROM public.arrangement_reviews
        WHERE arrangement_id=ANY(ARRAY[v_past_booking,v_past_reservation])), 'AC1-B1: expired arrangement flagged';
    -- AC1-B2 (boundary): the Singapore final day is included for both domains.
    ASSERT (SELECT count(*)=2 FROM public.arrangement_reviews
        WHERE arrangement_id=ANY(ARRAY[v_today_booking,v_today_reservation])), 'AC1-B2: final day excluded';
    -- AC1-B3 (boundary): future and already-started arrangements remain eligible through their final day.
    ASSERT (SELECT count(*)=2 FROM public.arrangement_reviews
        WHERE arrangement_id=ANY(ARRAY[v_future_booking,v_future_reservation])), 'AC1-B3: future arrangement excluded';

    SELECT array_agg(id) INTO v_old_ids FROM public.arrangement_reviews WHERE event_request_id=v_event;
    SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO v_flags FROM public.arrangement_reviews r WHERE id=ANY(v_old_ids);
    -- AC1-P1 (partition): venue text affects only venue targets and retains all older triggers.
    UPDATE public.event_requests SET venue_requirements='Auditorium' WHERE id=v_event;
    ASSERT (SELECT count(*)=2 AND count(DISTINCT trigger_id)=1
        AND bool_and(arrangement='venue_booking' AND changed_fields=ARRAY['venue_requirements']
                     AND trigger_type='event_change' AND strpos(reason,'Seminar room')>0 AND strpos(reason,'Auditorium')>0
                     AND cleared_at IS NULL AND cleared_by IS NULL)
        FROM public.arrangement_reviews WHERE event_request_id=v_event AND NOT(id=ANY(v_old_ids))),
        'AC1-P1: venue-only change mapped incorrectly';
    SELECT trigger_id INTO v_trigger FROM public.arrangement_reviews
        WHERE event_request_id=v_event AND NOT(id=ANY(v_old_ids)) LIMIT 1;
    ASSERT v_trigger<>v_first_trigger, 'AC1-P1: distinct accepted change reused prior trigger';
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r WHERE id=ANY(v_old_ids))=v_flags,
        'AC1-P1: earlier review evidence changed';

    SELECT array_agg(id) INTO v_old_ids FROM public.arrangement_reviews WHERE event_request_id=v_event;
    -- AC1-P2 (partition): equipment text affects only reservations, not approved venue bookings.
    UPDATE public.event_requests SET equipment_requirements='Projector' WHERE id=v_event;
    ASSERT (SELECT count(*)=2 AND count(DISTINCT trigger_id)=1
        AND bool_and(arrangement='equipment_reservation' AND changed_fields=ARRAY['equipment_requirements']
                     AND trigger_type='event_change' AND strpos(reason,'Microphone')>0 AND strpos(reason,'Projector')>0
                     AND cleared_at IS NULL AND cleared_by IS NULL)
        FROM public.arrangement_reviews WHERE event_request_id=v_event AND NOT(id=ANY(v_old_ids))),
        'AC1-P2: equipment-only change mapped incorrectly';

    -- AC1-H1 (happy): attendance independently affects both domains and never clears preceding work.
    SELECT array_agg(id) INTO v_old_ids FROM public.arrangement_reviews WHERE event_request_id=v_event;
    SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO v_flags FROM public.arrangement_reviews r WHERE id=ANY(v_old_ids);
    UPDATE public.event_requests SET expected_attendance=40 WHERE id=v_event;
    ASSERT (SELECT count(*)=4 AND count(DISTINCT trigger_id)=1
        AND bool_and(changed_fields=ARRAY['expected_attendance'] AND trigger_type='event_change'
                     AND strpos(reason,'25')>0 AND strpos(reason,'40')>0)
        FROM public.arrangement_reviews WHERE event_request_id=v_event AND NOT(id=ANY(v_old_ids))),
        'AC1-H1: attendance change must affect both domains';
    ASSERT (SELECT count(DISTINCT trigger_id)=4 AND count(*)=12 FROM public.arrangement_reviews WHERE event_request_id=v_event),
        'AC1-H1: distinct accepted updates lost or duplicated review work';
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r WHERE id=ANY(v_old_ids))=v_flags,
        'AC1-H1: subsequent update changed older work';

    -- AC1-P1, AC1-P2 (partition): one mixed-domain update records only each target's relevant changed fields/values.
    SELECT array_agg(id) INTO v_old_ids FROM public.arrangement_reviews WHERE event_request_id=v_event;
    UPDATE public.event_requests SET venue_requirements='Lecture theatre',equipment_requirements='Speakers'
        WHERE id=v_event;
    ASSERT (SELECT count(*)=2 AND bool_and(changed_fields=ARRAY['venue_requirements']
        AND strpos(reason,'Auditorium')>0 AND strpos(reason,'Lecture theatre')>0
        AND NOT('equipment_requirements'=ANY(changed_fields)))
        FROM public.arrangement_reviews WHERE event_request_id=v_event AND arrangement='venue_booking'
          AND NOT(id=ANY(v_old_ids))), 'AC1-P1: mixed update leaked irrelevant equipment fields into venue review';
    ASSERT (SELECT count(*)=2 AND bool_and(changed_fields=ARRAY['equipment_requirements']
        AND strpos(reason,'Projector')>0 AND strpos(reason,'Speakers')>0
        AND NOT('venue_requirements'=ANY(changed_fields)))
        FROM public.arrangement_reviews WHERE event_request_id=v_event AND arrangement='equipment_reservation'
          AND NOT(id=ANY(v_old_ids))), 'AC1-P2: mixed update leaked irrelevant venue fields into equipment review';
    ASSERT (SELECT count(*)=4 AND count(DISTINCT trigger_id)=1 FROM public.arrangement_reviews
        WHERE event_request_id=v_event AND NOT(id=ANY(v_old_ids))), 'AC1-P1/P2: mixed update split or duplicated trigger';

    SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO v_flags FROM public.arrangement_reviews r;
    SELECT coalesce(jsonb_agg(to_jsonb(n) ORDER BY id),'[]') INTO v_notices FROM public.notifications n;
    SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY id),'[]') INTO v_outbox FROM public.event_request_outbox o;
    -- AC2-N1 (negative): equivalent instants, equal attendance and outer-trim text are not significant changes.
    UPDATE public.event_requests SET
        proposed_date_times=ARRAY[(to_char((v_date+INTERVAL '1 day') AT TIME ZONE 'Asia/Singapore',
                                  'YYYY-MM-DD"T"HH24:MI:SS')||'+08:00')::timestamptz],
        expected_attendance=40,venue_requirements='  Lecture theatre  ',equipment_requirements=' Speakers '
        WHERE id=v_event;
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r)=v_flags,
        'AC2-N1: semantic no-op changed review evidence';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(n) ORDER BY id),'[]') FROM public.notifications n)=v_notices,
        'AC2-N1: no-op changed notifications';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY id),'[]') FROM public.event_request_outbox o)=v_outbox,
        'AC2-N1: no-op changed outbox';
    -- AC2-N2 (negative): unrelated text edits preserve flags and all existing notification state.
    UPDATE public.event_requests SET description='VERIFY unrelated description change' WHERE id=v_event;
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r)=v_flags,
        'AC2-N2: unrelated edit changed review evidence';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(n) ORDER BY id),'[]') FROM public.notifications n)=v_notices,
        'AC2-N2: unrelated edit changed notifications';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY id),'[]') FROM public.event_request_outbox o)=v_outbox,
        'AC2-N2: unrelated edit changed outbox';

    -- AC2-P1 (partition): Draft/terminal events and pending/rejected venue requests are ineligible.
    FOREACH v_ineligible_event IN ARRAY v_ineligible LOOP
        UPDATE public.event_requests SET expected_attendance=40 WHERE id=v_ineligible_event;
        ASSERT NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=v_ineligible_event),
            'AC2-P1: Draft/terminal event received reviews';
    END LOOP;
    ASSERT NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE arrangement_id=ANY(ARRAY[v_pending,v_rejected])),
        'AC2-P1: pending/rejected booking received review';
    ASSERT pg_temp.scrum64_protected_state()=v_before,
        'AC1/AC2: detail edits mutated resource rows or lifecycle history';
    ASSERT (SELECT status='Planning' FROM public.event_requests WHERE id=v_event),
        'AC1/AC2: flagging transitioned the event';

    -- AC1-X1 (cross-cutting): failure on the second actual flag rolls back the event update and first flag together.
    SELECT to_jsonb(e) INTO v_event_before FROM public.event_requests e WHERE id=v_atomic;
    SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO v_flags FROM public.arrangement_reviews r;
    SELECT coalesce(jsonb_agg(to_jsonb(n) ORDER BY id),'[]') INTO v_notices FROM public.notifications n;
    SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY id),'[]') INTO v_outbox FROM public.event_request_outbox o;
    PERFORM set_config('scrum64.atomic_event',v_atomic::text,true);
    BEGIN
        UPDATE public.event_requests SET expected_attendance=40 WHERE id=v_atomic;
        RAISE EXCEPTION 'AC1-X1: expected injected second flag failure';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT;
        ASSERT v_message='SCRUM64 injected second flag failure', 'AC1-X1: wrong failure caught';
    END;
    ASSERT currval('pg_temp.scrum64_flag_attempts')=2, 'AC1-X1: did not reach second flag';
    ASSERT (SELECT to_jsonb(e) FROM public.event_requests e WHERE id=v_atomic)=v_event_before,
        'AC1-X1: rejected update left event changes';
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r)=v_flags,
        'AC1-X1: rejected update left partial flag';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(n) ORDER BY id),'[]') FROM public.notifications n)=v_notices,
        'AC1-X1: failure changed notification state';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY id),'[]') FROM public.event_request_outbox o)=v_outbox,
        'AC1-X1: failure changed outbox';
    ASSERT pg_temp.scrum64_protected_state()=v_before, 'AC1-X1: failure mutated resources/history';
    RAISE NOTICE 'SCRUM64 event-change flag verification PASSED (10 existing case IDs)';
END $$;
ROLLBACK;
