-- SCRUM-40 approved 23 October: elapsed 168-hour boundary, system history and no domain side effects.
-- Owned disposable database ONLY: local history-failure trigger must never run on shared infrastructure.
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
 ASSERT to_regprocedure('public.complete_overdue_event_request(uuid,timestamp with time zone)') IS NOT NULL,
  'SETUP: production-owned callable completion scaffold required; missing routine is not feature Red';
END $$;
CREATE FUNCTION pg_temp.completion_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_requests x),
 'history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_status_history x),
 'changes',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_change_requests x),
 'assignments',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_coordinator_assignments x),
 'venues',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venues x),
 'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_booking_requests x),
 'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment x),
 'equipment_history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_status_history x),
 'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_requirements x),
 'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_reservations x),
 'registrations',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_registrations x),
 'registration_reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_registration_reviews x),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.arrangement_reviews x),
 'review_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x),
 'submission_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_outbox x),
 'inbox',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.notifications x));
$$;
CREATE FUNCTION pg_temp.completion_history_fault() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.event_request_id::text=current_setting('scrum40.history_fault_event',true) AND NEW.new_status='Completed' THEN
  RAISE EXCEPTION 'VERIFY40 required automatic history failure' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER verify40_history_fault BEFORE INSERT ON public.event_request_status_history
 FOR EACH ROW EXECUTE FUNCTION pg_temp.completion_history_fault();
DO $cases$
DECLARE
 owner_id uuid; e uuid; other uuid; b uuid; venue uuid; booking uuid; equipment uuid; requirement uuid;
 before_state jsonb; before_event jsonb; expected jsonb; history_row public.event_request_status_history;
 changed boolean; v_status text; caller text; msg text;
 as_of timestamptz:='2026-10-23T04:00:00Z'; end_at timestamptz; started timestamptz;
 today date:=(transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
BEGIN
 SELECT id INTO owner_id FROM auth.users ORDER BY id LIMIT 1;
 ASSERT owner_id IS NOT NULL, 'SETUP: disposable Auth FK identity required';
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance,final_event_end_at,
   registration_capacity,registration_opens_at,registration_closes_at)
 VALUES(owner_id,'VERIFY40 due confirmed','Confirmed',25,'2026-10-16T03:59:59.999999Z',100,now()-interval '1 day',now()+interval '1 day') RETURNING id INTO e;
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(owner_id,'VERIFY40 unrelated event','Planning',25) RETURNING id INTO other;
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
 VALUES(e,owner_id::text,'verify40');
 INSERT INTO public.venues(name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES('VERIFY40 retained venue','Test wing',100,'{}','{}','{theatre}','{AM,PM}') RETURNING id INTO venue;
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,start_minute,end_minute,status,decided_by,decided_at)
 VALUES(venue,owner_id,e,today+30,today+30,'{AM}',600,720,'approved',owner_id,now()) RETURNING id INTO booking;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('VERIFY40 retained microphone',10,'Test store',owner_id) RETURNING id INTO equipment;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(e,'VERIFY40 retained microphone',2,owner_id) RETURNING id INTO requirement;
 INSERT INTO public.equipment_reservations(equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(equipment,requirement,e,1,today+30,today+30,owner_id);
 INSERT INTO public.event_registrations(event_request_id,attendee_id) VALUES(e,owner_id);
 -- Retained storage controls only: completion must preserve prior decision and acknowledged registration evidence.
 INSERT INTO public.event_change_requests(event_request_id,organiser_id,status,explanation,proposed_changes,
  base_event_updated_at,coordinator_id,decision_reason,decided_at)
 SELECT e,owner_id,'Rejected','VERIFY40 retained proposal',jsonb_build_object('expected_attendance',40),
  updated_at,owner_id::text,'VERIFY40 retained rejection reason',clock_timestamp()
 FROM public.event_requests WHERE id=e;
 INSERT INTO public.event_registration_reviews(event_request_id,event_updated_at,changed_fields,reason,raised_at,cleared_at,cleared_by)
 SELECT e,updated_at,ARRAY['registration_needs'],'VERIFY40 retained registration acknowledgement',transaction_timestamp(),clock_timestamp(),owner_id
 FROM public.event_requests WHERE id=e;
 INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
 VALUES(e,'venue_booking',booking,gen_random_uuid(),'event_change',ARRAY['expected_attendance'],'VERIFY40 existing review remains outstanding');
 INSERT INTO public.event_request_outbox(event_request_id,organiser_id,event_type,payload)
 VALUES(e,owner_id,'event_request.submitted',jsonb_build_object('event_request_id',e));
 INSERT INTO public.notifications(recipient_id,event_type,payload,event_id)
 VALUES(owner_id::text,'event_request_submitted',jsonb_build_object('event_request_id',e),gen_random_uuid()::text);
 before_state:=pg_temp.completion_state();
 ASSERT jsonb_array_length(before_state->'bookings')>0 AND jsonb_array_length(before_state->'reservations')>0
  AND jsonb_array_length(before_state->'registrations')>0 AND jsonb_array_length(before_state->'review_jobs')>0
  AND jsonb_array_length(before_state->'submission_jobs')>0 AND jsonb_array_length(before_state->'inbox')>0
  AND EXISTS(SELECT 1 FROM public.event_change_requests WHERE event_request_id=e AND status='Rejected')
  AND EXISTS(SELECT 1 FROM public.event_registration_reviews WHERE event_request_id=e AND cleared_at IS NOT NULL AND cleared_by=owner_id),
  'SETUP: no-side-effect controls must be nonempty';
 before_event:=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=e);

 -- AC1-H1 (happy): one microsecond overdue completes with exact system audit at actual execution time and no other domain changes.
 started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 changed:=public.complete_overdue_event_request(e,as_of);
 RESET ROLE;
 ASSERT (SELECT status='Completed' FROM public.event_requests WHERE id=e), 'AC1-H1: due Confirmed event was not persisted as Completed';
 ASSERT changed IS TRUE, 'AC1-H1: successful completion did not report its transition';
 expected:=before_event||jsonb_build_object('status','Completed','updated_at',(SELECT updated_at FROM public.event_requests WHERE id=e));
 ASSERT (SELECT to_jsonb(r)=expected AND updated_at> (before_event->>'updated_at')::timestamptz FROM public.event_requests r WHERE id=e),
  'AC1-H1: completion changed event fields beyond status/version or failed to advance version';
 SELECT * INTO history_row FROM public.event_request_status_history WHERE event_request_id=e AND new_status='Completed';
 ASSERT history_row.previous_status='Confirmed' AND history_row.entry_kind='transition' AND history_row.actor_id IS NULL
  AND history_row.actor_role='system' AND history_row.source='event_request.auto_completed'
  AND history_row.occurred_at BETWEEN started AND clock_timestamp(), 'AC1-H1: automatic identity/source/actual completion timestamp incorrect';
 ASSERT (SELECT count(*) FROM public.event_request_status_history)=jsonb_array_length(before_state->'history')+1,
  'AC1-H1: completion did not add exactly one history entry';
 ASSERT NOT EXISTS(SELECT 1 FROM jsonb_array_elements(before_state->'history') old
  WHERE NOT EXISTS(SELECT 1 FROM public.event_request_status_history h WHERE to_jsonb(h)=old)), 'AC1-H1: earlier immutable history changed';
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_requests r WHERE id<>e)
  =(SELECT coalesce(jsonb_agg(r ORDER BY r->>'id'),'[]') FROM jsonb_array_elements(before_state->'events') r WHERE r->>'id'<>e::text),
  'AC1-H1: unrelated event changed';
 ASSERT pg_temp.completion_state()-ARRAY['events','history']=before_state-ARRAY['events','history'],
  'AC1-H1: automatic completion mutated resources, registrations, reviews, assignments, notices or delivery work';
 RAISE NOTICE 'PASS AC1-H1 / AC1-B3';

 -- AC7-N1 (negative): repetition preserves the entire first transition and all protected state.
 before_state:=pg_temp.completion_state();
 SET LOCAL ROLE service_role; changed:=public.complete_overdue_event_request(e,as_of+interval '1 hour'); RESET ROLE;
 ASSERT changed IS FALSE AND pg_temp.completion_state()=before_state, 'AC7-N1: repeated completion changed retained state';
 RAISE NOTICE 'PASS AC7-N1';

 -- AC1-B1/B2 (boundary): just short and exactly 168 elapsed hours refuse, including equivalent offset input and a DST crossing.
 FOREACH end_at IN ARRAY ARRAY['2026-10-16T04:00:00.000001Z'::timestamptz,'2026-10-16T12:00:00+08:00'::timestamptz] LOOP
  INSERT INTO public.event_requests(organiser_id,event_name,status,final_event_end_at)
  VALUES(owner_id,'VERIFY40 threshold','Confirmed',end_at) RETURNING id INTO b;
  before_state:=pg_temp.completion_state();
  SET LOCAL ROLE service_role; changed:=public.complete_overdue_event_request(b,as_of); RESET ROLE;
  ASSERT changed IS FALSE AND pg_temp.completion_state()=before_state, 'AC1-B1/B2: premature completion at or before threshold';
 END LOOP;
 INSERT INTO public.event_requests(organiser_id,event_name,status,final_event_end_at)
 VALUES(owner_id,'VERIFY40 elapsed DST threshold','Confirmed','2026-03-07T17:30:00Z') RETURNING id INTO b;
 before_state:=pg_temp.completion_state();
 SET LOCAL TIME ZONE 'America/New_York';
 SET LOCAL ROLE service_role; changed:=public.complete_overdue_event_request(b,'2026-03-14T17:00:00Z'); RESET ROLE;
 SET LOCAL TIME ZONE 'UTC';
 ASSERT changed IS FALSE AND pg_temp.completion_state()=before_state, 'AC1-B1: calendar days substituted for 168 elapsed hours across DST';
 RAISE NOTICE 'PASS AC1-B1 / AC1-B2';

 -- AC2-P1 (partition): every other existing lifecycle status is protected despite an overdue end.
 FOREACH v_status IN ARRAY ARRAY['Draft','Submitted','Under Review','Changes Requested','Approved','Planning','Safety Review','Completed','Cancelled','Rejected'] LOOP
  INSERT INTO public.event_requests(organiser_id,event_name,status,final_event_end_at)
  VALUES(owner_id,'VERIFY40 protected lifecycle',v_status,'2026-10-01T00:00:00Z') RETURNING id INTO b;
  before_state:=pg_temp.completion_state();
  SET LOCAL ROLE service_role; changed:=public.complete_overdue_event_request(b,as_of); RESET ROLE;
  ASSERT changed IS FALSE AND pg_temp.completion_state()=before_state, 'AC2-P1: non-Confirmed lifecycle mutated: '||v_status;
 END LOOP;
 RAISE NOTICE 'PASS AC2-P1';

 -- AC1-N1 (negative): legacy Confirmed without an authoritative end never derives one from other dates/resources.
 INSERT INTO public.event_requests(organiser_id,event_name,status,proposed_date_times)
 VALUES(owner_id,'VERIFY40 legacy missing end','Confirmed',ARRAY['2020-01-01T00:00:00Z'::timestamptz]) RETURNING id INTO b;
 before_state:=pg_temp.completion_state();
 SET LOCAL ROLE service_role; changed:=public.complete_overdue_event_request(b,as_of); RESET ROLE;
 ASSERT changed IS FALSE AND pg_temp.completion_state()=before_state, 'AC1-N1: missing final end was guessed or changed';
 RAISE NOTICE 'PASS AC1-N1';

 -- AC3-X1 (cross-cutting): failure of required immutable history rolls back status/version and every related row.
 INSERT INTO public.event_requests(organiser_id,event_name,status,final_event_end_at)
 VALUES(owner_id,'VERIFY40 history atomicity','Confirmed','2026-10-01T00:00:00Z') RETURNING id INTO b;
 PERFORM set_config('scrum40.history_fault_event',b::text,true);
 before_state:=pg_temp.completion_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.complete_overdue_event_request(b,as_of); RESET ROLE;
  RAISE EXCEPTION 'AC3-X1: required history failure was not raised' USING ERRCODE='P9940';
 EXCEPTION WHEN SQLSTATE '23514' THEN
  GET STACKED DIAGNOSTICS msg=MESSAGE_TEXT;
  ASSERT msg='VERIFY40 required automatic history failure', 'AC3-X1: unrelated constraint mistaken for injected history failure';
 END;
 ASSERT pg_temp.completion_state()=before_state, 'AC3-X1: failed history left a partial completion';
 PERFORM set_config('scrum40.history_fault_event','',true);
 RAISE NOTICE 'PASS AC3-X1';

 -- AC3-X2 (cross-cutting): browser roles cannot invoke the trusted worker or forge immutable completion history.
 FOREACH caller IN ARRAY ARRAY['anon','authenticated'] LOOP
  ASSERT NOT has_function_privilege(caller,'public.complete_overdue_event_request(uuid,timestamp with time zone)','EXECUTE'),
   'AC3-X2: browser granted automatic completion execution';
  before_state:=pg_temp.completion_state();
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',caller);
   PERFORM public.complete_overdue_event_request(b,as_of);
   RAISE EXCEPTION 'AC3-X2: browser executed automatic completion' USING ERRCODE='P9940';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  ASSERT pg_temp.completion_state()=before_state, 'AC3-X2: denied browser call changed protected state';
 END LOOP;
 ASSERT has_function_privilege('service_role','public.complete_overdue_event_request(uuid,timestamp with time zone)','EXECUTE'),
  'AC3-X2: trusted system boundary is unavailable';
 before_state:=pg_temp.completion_state();
 BEGIN
  UPDATE public.event_request_status_history SET source='forged' WHERE id=history_row.id;
  RAISE EXCEPTION 'AC3-X2: automatic history was mutable' USING ERRCODE='P9940';
 EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
 ASSERT pg_temp.completion_state()=before_state, 'AC3-X2: refused history tamper changed state';
 RAISE NOTICE 'PASS AC3-X2';
END $cases$;
ROLLBACK;
