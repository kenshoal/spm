-- SCRUM64 AC7: trusted transaction-internal explicit safety targets -> durable reviews.
-- Disposable PG only, README19-migration baseline and production-owned private helper.
-- psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_safety_rechecks.sql
-- No actual saved-decision caller/table, SafetyOfficer HTTP auth or lifecycle decision is mocked/proved.
BEGIN;
CREATE TEMP SEQUENCE scrum64_safety_insert_attempts;
CREATE FUNCTION pg_temp.scrum64_safety_count_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_attempt bigint;
BEGIN
 v_attempt:=nextval('pg_temp.scrum64_safety_insert_attempts');
 IF NEW.trigger_id::text=current_setting('scrum64.safety_fault_decision',true)
    AND v_attempt=current_setting('scrum64.safety_fault_at',true)::bigint THEN
   RAISE EXCEPTION 'SCRUM64 injected second safety flag failure' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER scrum64_test_safety_insert BEFORE INSERT ON public.arrangement_reviews
 FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum64_safety_count_insert();
CREATE FUNCTION pg_temp.scrum64_safety_snapshot() RETURNS jsonb
LANGUAGE sql STABLE AS $$
SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_requests r),
 'lifecycle',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_status_history r),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r),
 'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.venue_booking_requests r),
 'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_reservations r),
 'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_requirements r),
 'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment r),
 'equipment_history',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_status_history r),
 'notifications',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.notifications r),
 'outbox',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_outbox r)
);
$$;
DO $$
DECLARE
 v_actor uuid;
 v_event uuid;
 v_other uuid;
 v_decision uuid:=gen_random_uuid();
 v_later_decision uuid:=gen_random_uuid();
 v_atomic_decision uuid:=gen_random_uuid();
 v_venue uuid;
 v_booking uuid;
 v_unrelated_booking uuid;
 v_equipment uuid;
 v_requirement uuid;
 v_reservation uuid;
 v_other_reservation uuid;
 v_targets jsonb;
 v_bad jsonb;
 v_reason text:='Recheck emergency access; retain the complete specific safety instruction.';
 v_today date:=(transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
 v_before jsonb;
 v_protected jsonb;
 v_old_reviews jsonb;
 v_after jsonb;
 v_venue_review uuid;
 v_count integer;
 v_attempts bigint;
 v_message text;
 v_missing_message text;
 v_role text;
 v_helper oid:=to_regprocedure('private.raise_safety_arrangement_reviews(uuid,uuid,jsonb,text)');
BEGIN
 ASSERT v_helper IS NOT NULL, 'AC7 setup: private helper must exist before behavioural verification';
 SELECT id INTO v_actor FROM auth.users ORDER BY id LIMIT 1;
 ASSERT v_actor IS NOT NULL, 'fixture: disposable auth identity required';
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(v_actor,'VERIFY SCRUM64 explicit safety main','Safety Review',25) RETURNING id INTO v_event;
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(v_actor,'VERIFY SCRUM64 explicit safety other','Planning',25) RETURNING id INTO v_other;
 INSERT INTO public.venues(name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES('VERIFY SCRUM64 explicit safety venue','Test wing',100,'{}','{}',
  ARRAY['theatre']::public.room_layout[],ARRAY['AM']::public.booking_slot[]) RETURNING id INTO v_venue;
 -- Past/pending rows are deliberate: an explicit safety target is not AC1 ordinary date/approval selection.
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,status)
 VALUES(v_venue,v_actor,v_event,v_today-3,v_today-2,ARRAY['AM']::public.booking_slot[],'pending') RETURNING id INTO v_booking;
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,status)
 VALUES(v_venue,v_actor,v_event,v_today,v_today+1,ARRAY['AM']::public.booking_slot[],'pending') RETURNING id INTO v_unrelated_booking;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('VERIFY SCRUM64 explicit safety microphone',10,'Test store',v_actor) RETURNING id INTO v_equipment;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(v_event,'VERIFY SCRUM64 explicit safety microphone',10,v_actor) RETURNING id INTO v_requirement;
 INSERT INTO public.equipment_reservations(equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(v_equipment,v_requirement,v_event,1,v_today-3,v_today-2,v_actor) RETURNING id INTO v_reservation;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(v_other,'VERIFY SCRUM64 explicit safety microphone',10,v_actor) RETURNING id INTO v_requirement;
 INSERT INTO public.equipment_reservations(equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(v_equipment,v_requirement,v_other,1,v_today,v_today+1,v_actor) RETURNING id INTO v_other_reservation;
 v_targets:=jsonb_build_array(
  jsonb_build_object('arrangement','venue_booking','id',v_booking),
  jsonb_build_object('arrangement','equipment_reservation','id',v_reservation),
  jsonb_build_object('arrangement','venue_booking','id',v_booking));
 v_before:=pg_temp.scrum64_safety_snapshot();
 v_protected:=v_before-'reviews';

 -- AC7-H1 (happy): explicit mixed-domain targets share the actual supplied decision cause and do not select unrelated arrangements.
 v_count:=private.raise_safety_arrangement_reviews(v_event,v_decision,v_targets,v_reason);
 ASSERT (SELECT count(*)=2 FROM public.arrangement_reviews WHERE trigger_type='safety_recheck' AND trigger_id=v_decision),
  'AC7-H1: explicit safety action must persist two named arrangement reviews';
 ASSERT v_count=2, 'AC7-H1: inserted count must deduplicate repeated domain/UUID pairs';
 ASSERT (SELECT count(*)=2 AND bool_and(event_request_id=v_event AND trigger_type='safety_recheck'
  AND trigger_id=v_decision AND changed_fields=ARRAY[]::text[] AND reason=v_reason
  AND raised_at>=transaction_timestamp() AND raised_at<=clock_timestamp()
  AND cleared_at IS NULL AND cleared_by IS NULL
  AND ((arrangement='venue_booking' AND arrangement_id=v_booking)
    OR (arrangement='equipment_reservation' AND arrangement_id=v_reservation)))
  FROM public.arrangement_reviews WHERE trigger_id=v_decision), 'AC7-H1: explicit target/cause/full reason evidence differs';
 ASSERT NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE arrangement_id IN(v_unrelated_booking,v_other_reservation)),
  'AC7-H1: helper selected unrequested or wrong-event arrangements';
 ASSERT pg_temp.scrum64_safety_snapshot()-'reviews'=v_protected,
  'AC7-H1: flagging changed event lifecycle, arrangements or unrelated state';

 -- AC7-B1 (boundary): an explicit empty target set records no review work with valid required identity/reason inputs.
 v_before:=pg_temp.scrum64_safety_snapshot();
 v_count:=private.raise_safety_arrangement_reviews(v_event,gen_random_uuid(),'[]',v_reason);
 ASSERT v_count=0 AND pg_temp.scrum64_safety_snapshot()=v_before, 'AC7-B1: empty target set wrote review or other state';

 -- AC7-X1 (cross-cutting): replay preserves cleared audit/original evidence, while a genuinely distinct cause adds new work.
 SELECT id INTO STRICT v_venue_review FROM public.arrangement_reviews
  WHERE trigger_id=v_decision AND arrangement='venue_booking' AND arrangement_id=v_booking;
 SET LOCAL ROLE service_role;
 PERFORM public.clear_arrangement_review(v_venue_review,v_actor,ARRAY['venue_booking']);
 RESET ROLE;
 v_before:=pg_temp.scrum64_safety_snapshot();
 v_count:=private.raise_safety_arrangement_reviews(v_event,v_decision,v_targets,'A replay must not overwrite original evidence');
 ASSERT v_count=0 AND pg_temp.scrum64_safety_snapshot()=v_before,
  'AC7-X1: repeated cause duplicated, reopened or rewrote completed/original review evidence';
 SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO v_old_reviews FROM public.arrangement_reviews r WHERE trigger_id=v_decision;
 v_count:=private.raise_safety_arrangement_reviews(v_event,v_later_decision,
  jsonb_build_array(jsonb_build_object('arrangement','venue_booking','id',v_booking)),v_reason);
 ASSERT v_count=1 AND (SELECT count(*)=1 AND bool_and(cleared_at IS NULL AND cleared_by IS NULL)
  FROM public.arrangement_reviews WHERE trigger_id=v_later_decision AND arrangement_id=v_booking),
  'AC7-X1: distinct decision did not retain separate outstanding work';
 ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r WHERE trigger_id=v_decision)=v_old_reviews,
  'AC7-X1: later decision changed earlier cause/audit';

 -- AC7-N2 (negative): malformed/null arguments and missing/cross-event targets fail specifically before any flag INSERT attempt.
 v_before:=pg_temp.scrum64_safety_snapshot();
 SELECT last_value INTO v_attempts FROM pg_temp.scrum64_safety_insert_attempts;
 FOR v_bad IN SELECT value FROM (VALUES
  (NULL::jsonb), ('{}'::jsonb), ('[null]'::jsonb),
  (jsonb_build_array(jsonb_build_object('arrangement','invalid_domain','id',v_booking))),
  (jsonb_build_array(jsonb_build_object('arrangement','venue_booking'))),
  (jsonb_build_array(jsonb_build_object('arrangement','venue_booking','id','not-a-uuid')))
 ) malformed(value) LOOP
  BEGIN
   PERFORM private.raise_safety_arrangement_reviews(v_event,gen_random_uuid(),v_bad,v_reason);
   RAISE EXCEPTION 'AC7-N2: malformed target input accepted';
  EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
  END;
  ASSERT pg_temp.scrum64_safety_snapshot()=v_before
    AND (SELECT last_value=v_attempts FROM pg_temp.scrum64_safety_insert_attempts),
    'AC7-N2: malformed input attempted a flag or changed state';
 END LOOP;
 BEGIN
  PERFORM private.raise_safety_arrangement_reviews(NULL,v_decision,'[]',v_reason);
  RAISE EXCEPTION 'AC7-N2: null event accepted';
 EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
 END;
 BEGIN
  PERFORM private.raise_safety_arrangement_reviews(v_event,NULL,'[]',v_reason);
  RAISE EXCEPTION 'AC7-N2: null decision accepted';
 EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
 END;
 BEGIN
  PERFORM private.raise_safety_arrangement_reviews(v_event,v_decision,'[]',NULL);
  RAISE EXCEPTION 'AC7-N2: null reason accepted for empty target list';
 EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
 END;
 BEGIN
  PERFORM private.raise_safety_arrangement_reviews(v_event,v_decision,'[]','  ');
  RAISE EXCEPTION 'AC7-N2: blank reason accepted for empty target list';
 EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
 END;
 BEGIN
  PERFORM private.raise_safety_arrangement_reviews(gen_random_uuid(),gen_random_uuid(),'[]',v_reason);
  RAISE EXCEPTION 'AC7-N2: missing event accepted';
 EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
 END;
 FOR v_bad IN SELECT value FROM (VALUES
  (jsonb_build_array(jsonb_build_object('arrangement','venue_booking','id',v_unrelated_booking),
    jsonb_build_object('arrangement','equipment_reservation','id',gen_random_uuid()))),
  (jsonb_build_array(jsonb_build_object('arrangement','venue_booking','id',v_unrelated_booking),
    jsonb_build_object('arrangement','equipment_reservation','id',v_other_reservation)))
 ) invalid(value) LOOP
  BEGIN
   PERFORM private.raise_safety_arrangement_reviews(v_event,gen_random_uuid(),v_bad,v_reason);
   RAISE EXCEPTION 'AC7-N2: missing/cross-event target accepted';
  EXCEPTION WHEN SQLSTATE 'P0002' THEN
   GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT;
   IF v_missing_message IS NULL THEN v_missing_message:=v_message;
   ELSE ASSERT v_message=v_missing_message, 'AC7-N2: missing/cross-event targets differ in private refusal'; END IF;
  END;
  ASSERT pg_temp.scrum64_safety_snapshot()=v_before
   AND (SELECT last_value=v_attempts FROM pg_temp.scrum64_safety_insert_attempts),
   'AC7-N2: invalid batch attempted first valid flag before complete validation';
 END LOOP;
 ASSERT pg_temp.scrum64_safety_snapshot()=v_before, 'AC7-N2: refused argument call changed protected state';

 -- AC7-X2 (cross-cutting): second actual flag failure rolls back the first flag and all protected state together.
 v_before:=pg_temp.scrum64_safety_snapshot();
 SELECT last_value INTO v_attempts FROM pg_temp.scrum64_safety_insert_attempts;
 PERFORM set_config('scrum64.safety_fault_decision',v_atomic_decision::text,true);
 PERFORM set_config('scrum64.safety_fault_at',(v_attempts+2)::text,true);
 BEGIN
  PERFORM private.raise_safety_arrangement_reviews(v_event,v_atomic_decision,v_targets,v_reason);
  RAISE EXCEPTION 'AC7-X2: expected second-flag failure';
 EXCEPTION WHEN check_violation THEN
  GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT;
  ASSERT v_message='SCRUM64 injected second safety flag failure', 'AC7-X2: unrelated failure caught';
 END;
 ASSERT (SELECT last_value=v_attempts+2 FROM pg_temp.scrum64_safety_insert_attempts),
  'AC7-X2: did not attempt the second actual flag';
 ASSERT pg_temp.scrum64_safety_snapshot()=v_before, 'AC7-X2: failed helper left partial flags or protected writes';

 -- AC7-X3 (cross-cutting): only a trusted privileged transaction may invoke the private writer, never app/browser roles directly.
 ASSERT (SELECT NOT prosecdef AND pronamespace='private'::regnamespace
  AND EXISTS(SELECT 1 FROM unnest(proconfig) c WHERE c IN('search_path=','search_path=""'))
  FROM pg_proc WHERE oid=v_helper), 'AC7-X3: helper is not a private INVOKER with empty search_path';
 FOREACH v_role IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
  ASSERT NOT has_function_privilege(v_role,v_helper,'EXECUTE'), 'AC7-X3: caller role granted direct helper EXECUTE';
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',v_role);
   PERFORM private.raise_safety_arrangement_reviews(v_event,v_decision,v_targets,v_reason);
   RAISE EXCEPTION 'AC7-X3: app/browser directly invoked safety helper';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
 END LOOP;
 ASSERT pg_temp.scrum64_safety_snapshot()=v_before, 'AC7-X3: refused direct invocation changed state';
 ASSERT NOT has_table_privilege('service_role','public.arrangement_reviews','INSERT')
  AND NOT has_table_privilege('service_role','public.arrangement_reviews','UPDATE'),
  'AC7-X3: safety helper broadened app-role review mutation grants';
 RAISE NOTICE 'SCRUM64 private safety-recheck verification PASSED (six case IDs; no caller/auth integration claim)';
END $$;
ROLLBACK;
