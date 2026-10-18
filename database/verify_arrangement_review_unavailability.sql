-- SCRUM-64 AC6: real audited equipment status RPC -> affected reservation reviews.
-- Disposable PostgreSQL only, after README prerequisites through 0031 and AC6 DDL.
-- psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_unavailability.sql
-- Fixtures, failure injector and vanilla-PG service grants all roll back.
BEGIN;
-- Supabase's service table defaults are absent from vanilla PostgreSQL fixtures.
GRANT SELECT, UPDATE ON public.equipment TO service_role;
GRANT SELECT, INSERT ON public.equipment_status_history TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.equipment_status_history_id_seq TO service_role;

CREATE TEMP SEQUENCE scrum64_unavailable_attempts;
CREATE FUNCTION pg_temp.scrum64_unavailable_fail_second() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.event_request_id::text = current_setting('scrum64.unavailable_atomic_event', true) THEN
        IF nextval('pg_temp.scrum64_unavailable_attempts')=2 THEN
            RAISE EXCEPTION 'SCRUM64 injected unavailable flag failure' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER scrum64_test_unavailable_failure BEFORE INSERT ON public.arrangement_reviews
    FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum64_unavailable_fail_second();

CREATE FUNCTION pg_temp.scrum64_unavailable_protected() RETURNS jsonb
LANGUAGE sql STABLE AS $$
SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_requests r),
 'lifecycle',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_status_history r),
 'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_requirements r),
 'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_reservations r),
 'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.venue_booking_requests r)
);
$$;
CREATE FUNCTION pg_temp.scrum64_unavailable_all() RETURNS jsonb
LANGUAGE sql STABLE AS $$
SELECT jsonb_build_object(
 'protected',pg_temp.scrum64_unavailable_protected(),
 'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment r),
 'history',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_status_history r),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r),
 'notifications',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.notifications r),
 'outbox',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_outbox r)
);
$$;
DO $$
DECLARE
 v_today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
 v_actor uuid;
 v_event uuid;
 v_other uuid;
 v_ineligible uuid;
 v_equipment uuid;
 v_other_equipment uuid;
 v_atomic_equipment uuid;
 v_atomic_event uuid;
 v_requirement uuid;
 v_reservation uuid;
 v_expected uuid[];
 v_excluded uuid[];
 v_new_ids uuid[];
 v_trigger uuid;
 v_prior_trigger uuid;
 v_writer record;
 v_writer_count integer:=0;
 v_status text;
 v_event_status text;
 v_offset integer;
 v_count integer;
 v_history_count integer;
 v_history jsonb;
 v_reviews jsonb;
 v_protected jsonb;
 v_other_history jsonb;
 v_other_equipment_state jsonb;
 v_all jsonb;
 v_message text;
BEGIN
 SELECT id INTO v_actor FROM auth.users ORDER BY id LIMIT 1;
 ASSERT v_actor IS NOT NULL, 'fixture: disposable auth identity required';

 FOREACH v_status IN ARRAY ARRAY['DAMAGED','UNDER_REPAIR','UNDER_MAINTENANCE','RETIRED'] LOOP
    v_expected:='{}'; v_excluded:='{}';
    INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
    VALUES(v_actor,'VERIFY SCRUM64 AC6 main '||v_status,'Planning',25) RETURNING id INTO v_event;
    INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
    VALUES(v_actor,'VERIFY SCRUM64 AC6 second '||v_status,'Submitted',25) RETURNING id INTO v_other;
    INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
    VALUES('VERIFY SCRUM64 AC6 same label',100,'Test store',v_actor) RETURNING id INTO v_equipment;
    INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
    VALUES('VERIFY SCRUM64 AC6 same label',100,'Other store',v_actor) RETURNING id INTO v_other_equipment;
    INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
    VALUES(v_event,'VERIFY SCRUM64 AC6 same label',100,v_actor) RETURNING id INTO v_requirement;
    FOR v_offset IN -1..1 LOOP
        INSERT INTO public.equipment_reservations
         (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
        VALUES(v_equipment,v_requirement,v_event,1,v_today+v_offset-2,v_today+v_offset,v_actor)
        RETURNING id INTO v_reservation;
        IF v_offset=-1 THEN v_excluded:=array_append(v_excluded,v_reservation);
        ELSE v_expected:=array_append(v_expected,v_reservation); END IF;
    END LOOP;
    INSERT INTO public.equipment_reservations
     (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
    VALUES(v_other_equipment,v_requirement,v_event,1,v_today-1,v_today+1,v_actor)
    RETURNING id INTO v_reservation;
    v_excluded:=array_append(v_excluded,v_reservation);
    INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
    VALUES(v_other,'VERIFY SCRUM64 AC6 same label',10,v_actor) RETURNING id INTO v_requirement;
    INSERT INTO public.equipment_reservations
     (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
    VALUES(v_equipment,v_requirement,v_other,1,v_today+1,v_today+2,v_actor)
    RETURNING id INTO v_reservation;
    v_expected:=array_append(v_expected,v_reservation);
    FOREACH v_event_status IN ARRAY ARRAY['Draft','Completed','Cancelled','Rejected'] LOOP
        INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
        VALUES(v_actor,'VERIFY SCRUM64 AC6 excluded '||v_event_status,v_event_status,25)
        RETURNING id INTO v_ineligible;
        INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
        VALUES(v_ineligible,'VERIFY SCRUM64 AC6 same label',10,v_actor) RETURNING id INTO v_requirement;
        INSERT INTO public.equipment_reservations
         (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
        VALUES(v_equipment,v_requirement,v_ineligible,1,v_today-1,v_today+1,v_actor)
        RETURNING id INTO v_reservation;
        v_excluded:=array_append(v_excluded,v_reservation);
    END LOOP;
    v_protected:=pg_temp.scrum64_unavailable_protected();
    SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') INTO v_other_history
        FROM public.equipment_status_history r WHERE equipment_id<>v_equipment;
    SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') INTO v_other_equipment_state
        FROM public.equipment r WHERE id<>v_equipment;
    SELECT coalesce(array_agg(id),'{}') INTO v_new_ids FROM public.arrangement_reviews;
    SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') INTO v_reviews FROM public.arrangement_reviews r;
    SELECT count(*) INTO v_history_count FROM public.equipment_status_history WHERE equipment_id=v_equipment;

    -- AC6-H1 (happy), AC6-P1 (partition): each audited unavailable action flags exact reservations across events.
    SET LOCAL ROLE service_role;
    PERFORM public.transition_equipment_status(v_equipment,v_status::varchar,v_actor,'VERIFY SCRUM64 AC6');
    RESET ROLE;
    SELECT count(*) INTO v_count FROM public.arrangement_reviews WHERE NOT(id=ANY(v_new_ids));
    ASSERT v_count=3, 'AC6-H1/P1: unavailable RPC must create three eligible reservation flags';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r
        WHERE id=ANY(v_new_ids))=v_reviews, 'AC6-H1: later equipment action rewrote prior reviews';
    ASSERT (SELECT count(*)=3 AND count(DISTINCT trigger_id)=1
        AND bool_and(arrangement='equipment_reservation' AND arrangement_id=ANY(v_expected)
            AND trigger_type='equipment_unavailable' AND changed_fields=ARRAY['operational_status']
            AND strpos(reason,'AVAILABLE')>0 AND strpos(reason,v_status)>0
            AND raised_at IS NOT NULL AND cleared_at IS NULL AND cleared_by IS NULL)
        FROM public.arrangement_reviews WHERE NOT(id=ANY(v_new_ids))),
        'AC6-H1/P1: wrong targets, shared cause or unavailable evidence';
    ASSERT NOT EXISTS(SELECT 1 FROM public.arrangement_reviews ar
        JOIN public.equipment_reservations r ON r.id=ar.arrangement_id
        WHERE NOT(ar.id=ANY(v_new_ids)) AND (ar.event_request_id<>r.event_request_id
            OR r.equipment_id<>v_equipment OR r.requirement_id IS NULL)),
        'AC6-H1: review lost actual event/equipment/requirement relationship';
    SELECT trigger_id INTO v_trigger FROM public.arrangement_reviews WHERE NOT(id=ANY(v_new_ids)) LIMIT 1;
    SELECT to_jsonb(h) INTO v_history FROM public.equipment_status_history h
        WHERE equipment_id=v_equipment ORDER BY id DESC LIMIT 1;
    ASSERT (SELECT count(*)=v_history_count+1 FROM public.equipment_status_history WHERE equipment_id=v_equipment)
        AND v_history->>'old_status'='AVAILABLE' AND v_history->>'new_status'=v_status
        AND v_history->>'changed_by'=v_actor::text,
        'AC6-H1/P1: normal equipment audit not preserved';
    ASSERT EXISTS(SELECT 1 FROM jsonb_each_text(v_history) e WHERE e.value=v_trigger::text),
        'AC6-H1: review cause must be attributable to the persisted status history';
    ASSERT (SELECT operational_status=v_status FROM public.equipment WHERE id=v_equipment),
        'AC6-H1/P1: operational status action did not persist';

    -- AC6-B1 (boundary): yesterday excluded, Singapore today and future/ongoing included.
    ASSERT NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE arrangement_id=ANY(v_excluded)),
        'AC6-B1: past, other-equipment or ineligible-event reservation flagged';
    ASSERT (SELECT count(*)=3 FROM public.arrangement_reviews WHERE arrangement_id=ANY(v_expected)),
        'AC6-B1: inclusive final-day or future reservation missing';
    ASSERT pg_temp.scrum64_unavailable_protected()=v_protected,
        'AC6-H1/P1: unavailable action mutated events, lifecycle history or resource arrangements';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_status_history r
        WHERE equipment_id<>v_equipment)=v_other_history,
        'AC6-H1/P1: unrelated equipment history changed';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment r
        WHERE id<>v_equipment)=v_other_equipment_state,
        'AC6-H1/P1: unrelated equipment changed';

    SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') INTO v_reviews FROM public.arrangement_reviews r;
    -- AC6-N2 (negative): repeated status, creation audits and ineligible links cannot create false review work.
    SET LOCAL ROLE service_role;
    PERFORM public.transition_equipment_status(v_equipment,v_status::varchar,v_actor,'VERIFY same status');
    RESET ROLE;
    INSERT INTO public.equipment_status_history(equipment_id,old_status,new_status,changed_by)
    VALUES(v_equipment,NULL,v_status,v_actor);
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r)=v_reviews,
        'AC6-N2: same status or creation audit reflagged reservations';
    -- AC6-N1 (negative): availability restoration never clears reviews or invents a new unavailable trigger.
    SET LOCAL ROLE service_role;
    PERFORM public.transition_equipment_status(v_equipment,'AVAILABLE'::varchar,v_actor,'VERIFY restoration');
    RESET ROLE;
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r)=v_reviews,
        'AC6-N1: restoration cleared or reflagged outstanding work';
    ASSERT pg_temp.scrum64_unavailable_protected()=v_protected,
        'AC6-N1/N2: restoration/repeat changed event or arrangement data';

    -- AC6-H1, AC6-N1 (happy/negative): later unavailability of the same row is a distinct cause retaining earlier evidence.
    v_prior_trigger:=v_trigger;
    SELECT coalesce(array_agg(id),'{}') INTO v_new_ids FROM public.arrangement_reviews;
    SET LOCAL ROLE service_role;
    PERFORM public.transition_equipment_status(v_equipment,v_status::varchar,v_actor,'VERIFY later distinct cause');
    RESET ROLE;
    ASSERT (SELECT count(*)=3 AND count(DISTINCT trigger_id)=1
        AND bool_and(trigger_id<>v_prior_trigger AND arrangement_id=ANY(v_expected)
            AND arrangement='equipment_reservation' AND trigger_type='equipment_unavailable'
            AND changed_fields=ARRAY['operational_status'] AND strpos(reason,'AVAILABLE')>0
            AND strpos(reason,v_status)>0 AND cleared_at IS NULL AND cleared_by IS NULL)
        FROM public.arrangement_reviews WHERE NOT(id=ANY(v_new_ids))),
        'AC6-H1: same equipment later cause reused, dropped or misattributed';
    SELECT trigger_id INTO v_trigger FROM public.arrangement_reviews WHERE NOT(id=ANY(v_new_ids)) LIMIT 1;
    SELECT to_jsonb(h) INTO v_history FROM public.equipment_status_history h
        WHERE equipment_id=v_equipment ORDER BY id DESC LIMIT 1;
    ASSERT v_history->>'old_status'='AVAILABLE' AND v_history->>'new_status'=v_status
        AND v_history->>'changed_by'=v_actor::text
        AND EXISTS(SELECT 1 FROM jsonb_each_text(v_history) e WHERE e.value=v_trigger::text),
        'AC6-H1: later cause is not attributable to its actual audit';
    ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r
        WHERE id=ANY(v_new_ids))=v_reviews,
        'AC6-H1/N1: distinct later trigger erased, cleared or rewrote older reviews';
    ASSERT pg_temp.scrum64_unavailable_protected()=v_protected,
        'AC6-H1: later cause changed lifecycle or arrangements';
 END LOOP;


 -- AC6-H1 (happy/security): the native audit writer works without direct caller EXECUTE or review-table writes.
 FOR v_writer IN
    SELECT p.oid,p.prosecdef,p.proconfig,n.nspname,format('%I.%I()',n.nspname,p.proname) AS invocation
    FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE t.tgrelid='public.equipment_status_history'::regclass AND NOT t.tgisinternal
      AND (t.tgtype::integer & 4)=4 AND (t.tgtype::integer & 2)=0
 LOOP
    v_writer_count:=v_writer_count+1;
    ASSERT v_writer.prosecdef AND v_writer.nspname='private'
        AND EXISTS(SELECT 1 FROM unnest(v_writer.proconfig) c WHERE c IN('search_path=','search_path=""')),
        'AC6-H1: audit writer lacks private SECURITY DEFINER/empty search_path';
    ASSERT NOT has_function_privilege('anon',v_writer.oid,'EXECUTE')
        AND NOT has_function_privilege('authenticated',v_writer.oid,'EXECUTE')
        AND NOT has_function_privilege('service_role',v_writer.oid,'EXECUTE'),
        'AC6-H1: native writer exposed as a directly callable function';
    BEGIN
        SET LOCAL ROLE anon;
        EXECUTE 'SELECT '||v_writer.invocation;
        RAISE EXCEPTION 'AC6-H1: browser directly executed native writer';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
 END LOOP;
 ASSERT v_writer_count>0, 'AC6-H1: no protected native history writer found';
 ASSERT NOT has_table_privilege('service_role','public.arrangement_reviews','INSERT')
    AND NOT has_table_privilege('service_role','public.arrangement_reviews','UPDATE')
    AND NOT has_table_privilege('authenticated','public.arrangement_reviews','INSERT'),
    'AC6-H1: native flagging broadened direct review-table write grants';

 -- AC6-X1 (cross-cutting): second-flag failure rolls back operational status, normal audit and all side effects.
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(v_actor,'VERIFY SCRUM64 AC6 atomic','Planning',25) RETURNING id INTO v_atomic_event;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('VERIFY SCRUM64 AC6 atomic',10,'Test store',v_actor) RETURNING id INTO v_atomic_equipment;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(v_atomic_event,'VERIFY SCRUM64 AC6 atomic',10,v_actor) RETURNING id INTO v_requirement;
 FOR v_offset IN 0..1 LOOP
    INSERT INTO public.equipment_reservations
     (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
    VALUES(v_atomic_equipment,v_requirement,v_atomic_event,1,v_today-1,v_today+v_offset,v_actor);
 END LOOP;
 v_all:=pg_temp.scrum64_unavailable_all();
 PERFORM set_config('scrum64.unavailable_atomic_event',v_atomic_event::text,true);
 BEGIN
    SET LOCAL ROLE service_role;
    PERFORM public.transition_equipment_status(v_atomic_equipment,'DAMAGED'::varchar,v_actor,'VERIFY rollback');
    RESET ROLE;
    RAISE EXCEPTION 'AC6-X1: expected injected second-flag failure';
 EXCEPTION WHEN check_violation THEN
    GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT;
    ASSERT v_message='SCRUM64 injected unavailable flag failure', 'AC6-X1: wrong failure caught';
 END;
 ASSERT currval('pg_temp.scrum64_unavailable_attempts')=2, 'AC6-X1: second actual flag was never attempted';
 ASSERT pg_temp.scrum64_unavailable_all()=v_all, 'AC6-X1: partial equipment/audit/review/resource/notification write survived';
 RAISE NOTICE 'SCRUM64 equipment-unavailability verification PASSED (six case IDs)';
END $$;
ROLLBACK;
