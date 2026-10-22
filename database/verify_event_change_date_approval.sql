-- SCRUM35 date/time application: actual saved decision, complete venue batch and required reviews/jobs.
-- Owned disposable PostgreSQL only: temporary fault trigger and fixtures must never run on shared infrastructure.
BEGIN;
SET LOCAL statement_timeout='25s';
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
 ASSERT to_regprocedure('public.approve_date_event_change_request(uuid,uuid,character varying,text,jsonb)') IS NOT NULL,
  'SETUP: frozen date transaction must be installed; absence is not feature Red';
END $$;
CREATE FUNCTION pg_temp.date_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_requests x),
 'changes',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_change_requests x),
 'assignments',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_coordinator_assignments x),
 'history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_status_history x),
 'registrations',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_registrations x),
 'registration_reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_registration_reviews x),
 'venue',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venues x),
 'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_booking_requests x),
 'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment x),
 'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_requirements x),
 'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_reservations x),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.arrangement_reviews x),
 'review_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x),
 'blocks',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_blocks x),
 'refusals',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_booking_refusals x),
 'timing',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_timing_changes x),
 'safety',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.safety_reviews x),
 'submission_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_outbox x),
 'inbox',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.notifications x));
$$;
CREATE FUNCTION pg_temp.date_unrelated(s jsonb,e uuid,c uuid) RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
 SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]') FROM jsonb_array_elements(s->'events') x WHERE x->>'id'<>e::text),
 'changes',(SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]') FROM jsonb_array_elements(s->'changes') x WHERE x->>'id'<>c::text),
 'reviews',(SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]') FROM jsonb_array_elements(s->'reviews') x WHERE x->>'event_request_id'<>e::text),
 'review_jobs',(SELECT coalesce(jsonb_agg(x ORDER BY x->>'review_id'),'[]') FROM jsonb_array_elements(s->'review_jobs') x WHERE x->>'event_request_id'<>e::text),
 'registration_reviews',(SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]') FROM jsonb_array_elements(s->'registration_reviews') x WHERE x->>'event_request_id'<>e::text));
$$;
CREATE FUNCTION pg_temp.date_fixture() RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
 o uuid; e uuid:=gen_random_uuid(); v uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); a uuid:=gen_random_uuid();
 inactive uuid:=gen_random_uuid(); rejected uuid:=gen_random_uuid(); eq uuid:=gen_random_uuid(); req uuid:=gen_random_uuid();
 past uuid:=gen_random_uuid(); future uuid:=gen_random_uuid(); cid uuid;
 d date:=(transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date+30;
BEGIN
 SELECT id INTO o FROM auth.users ORDER BY id LIMIT 1;
 ASSERT o IS NOT NULL,'SETUP: disposable Auth FK identity required';
 INSERT INTO public.event_requests(id,organiser_id,event_name,status,expected_attendance,venue_requirements,equipment_requirements,registration_needs,proposed_date_times)
 VALUES(e,o,'VERIFY35 date transaction','Planning',25,'Room','Microphone','Paper form',
  ARRAY[(d::text||'T10:00:00+08:00')::timestamptz,((d+1)::text||'T15:00:00+08:00')::timestamptz]);
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by) VALUES(e,o::text,'verify35');
 INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots,setup_minutes,turnaround_minutes)
 VALUES(v,'VERIFY35 date venue','Test wing',100,'{}','{}','{theatre}','{AM,PM,NIGHT}',15,15);
 INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,start_minute,end_minute,status,decided_by,decided_at)
 VALUES(b,v,o,e,d,d,600,690,'pending',NULL,NULL),(a,v,o,e,d+1,d+1,900,1050,'approved',o,now());
 INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,start_minute,end_minute,status,cancelled_by,cancelled_at)
 VALUES(inactive,v,o,e,d,d,600,690,'cancelled',o,now());
 INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,start_minute,end_minute,status,decided_by,decided_at,decision_reason)
 VALUES(rejected,v,o,e,d,d,600,690,'rejected',o,now(),'Retained rejected arrangement');
 INSERT INTO public.equipment(id,type,total_owned_quantity,home_location,created_by) VALUES(eq,'VERIFY35 date microphone',10,'Test store',o);
 INSERT INTO public.equipment_requirements(id,event_request_id,equipment_type,quantity,recorded_by) VALUES(req,e,'VERIFY35 date microphone',2,o);
 INSERT INTO public.equipment_reservations(id,equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(past,eq,req,e,1,d-40,d-31,o),(future,eq,req,e,1,d,d+5,o);
 SELECT id INTO cid FROM public.create_event_change_request(e,o,'Move both activity dates',
  jsonb_build_object('proposed_date_times',jsonb_build_array((d+2)::text||'T10:00:00+08:00',(d+3)::text||'T15:00:00+08:00')));
 RETURN jsonb_build_object('event',e,'owner',o,'venue',v,'pending',b,'approved',a,'cancelled',inactive,'rejected',rejected,'past',past,'future',future,'change',cid,'day',d);
END $$;
CREATE FUNCTION pg_temp.date_plan(f jsonb) RETURNS jsonb LANGUAGE sql AS $$
 SELECT jsonb_build_array(
  jsonb_build_object('booking_id',f->>'pending','start_date',((f->>'day')::date+2)::text,'end_date',((f->>'day')::date+2)::text,'start_minute',600,'end_minute',690),
  jsonb_build_object('booking_id',f->>'approved','start_date',((f->>'day')::date+3)::text,'end_date',((f->>'day')::date+3)::text,'start_minute',900,'end_minute',1050));
$$;
CREATE FUNCTION pg_temp.date_fault() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.event_request_id::text=current_setting('scrum35.date_fault_event',true) THEN
  RAISE EXCEPTION 'VERIFY35 required registration-review failure' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER verify35_date_fault BEFORE INSERT ON public.event_registration_reviews FOR EACH ROW EXECUTE FUNCTION pg_temp.date_fault();
DO $cases$
DECLARE
 f jsonb; before_state jsonb; before_event jsonb; original jsonb; expected jsonb; actual jsonb; plan jsonb; bad jsonb;
 saved public.event_change_requests; d date; started timestamptz; message text; detail text; issues jsonb;
 mode text; browser text; conflict uuid; block_id uuid; foreign_id uuid:=gen_random_uuid(); actor uuid;
BEGIN
 -- AC3-H5 (happy): automatic mapping moves the complete eligible batch, retains inactive rows/audit and records one atomic event cause across existing arrangements.
 f:=pg_temp.date_fixture(); d:=(f->>'day')::date; actor:=(f->>'owner')::uuid;
 before_state:=pg_temp.date_state(); before_event:=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=(f->>'event')::uuid);
 original:=(SELECT to_jsonb(r) FROM public.event_change_requests r WHERE id=(f->>'change')::uuid); plan:=pg_temp.date_plan(f); started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 saved:=public.approve_date_event_change_request((f->>'event')::uuid,(f->>'change')::uuid,actor::varchar,'Checked complete booking plan',NULL);
 RESET ROLE;
 ASSERT saved.status='Approved' AND saved.coordinator_id=actor::text AND saved.decision_reason='Checked complete booking plan'
  AND saved.decided_at BETWEEN started AND clock_timestamp(),'AC3-H5: approval actor/time/reason not saved';
 ASSERT to_jsonb(saved)-ARRAY['status','coordinator_id','decision_reason','decided_at','applied_booking_plan']
  =original-ARRAY['status','coordinator_id','decision_reason','decided_at','applied_booking_plan'],'AC3-H5: immutable proposal or provenance changed';
 ASSERT (SELECT to_jsonb(r)=to_jsonb(saved) FROM public.event_change_requests r WHERE id=saved.id),'AC3-H5: returned decision is not stored';
 ASSERT (SELECT jsonb_agg(x ORDER BY x->>'booking_id') FROM jsonb_array_elements(saved.applied_booking_plan) x)
  =(SELECT jsonb_agg(x ORDER BY x->>'booking_id') FROM jsonb_array_elements(plan) x),'AC3-H5: complete actual applied plan missing or invented';
 expected:=before_event||jsonb_build_object('proposed_date_times',to_jsonb(ARRAY[((d+2)::text||'T10:00:00+08:00')::timestamptz,((d+3)::text||'T15:00:00+08:00')::timestamptz]),'updated_at',(SELECT updated_at FROM public.event_requests WHERE id=saved.event_request_id));
 ASSERT (SELECT to_jsonb(r)=expected AND updated_at>saved.base_event_updated_at FROM public.event_requests r WHERE id=saved.event_request_id),'AC3-H5: event dates/version not applied exactly or lifecycle changed';
 FOR actual IN SELECT value FROM jsonb_array_elements(before_state->'bookings') LOOP
  expected:=actual;
  IF actual->>'id'=f->>'pending' THEN expected:=actual||jsonb_build_object('start_date',(d+2)::text,'end_date',(d+2)::text);
  ELSIF actual->>'id'=f->>'approved' THEN expected:=actual||jsonb_build_object('start_date',(d+3)::text,'end_date',(d+3)::text); END IF;
  ASSERT (SELECT to_jsonb(r)=expected FROM public.venue_booking_requests r WHERE id=(actual->>'id')::uuid),'AC3-H5: eligible shift lost minutes/audit or modified another/inactive booking';
 END LOOP;
 ASSERT (SELECT count(*)=3 AND count(DISTINCT trigger_id)=1 AND bool_and(trigger_type='event_change'
  AND changed_fields=ARRAY['proposed_date_times'] AND cleared_at IS NULL AND cleared_by IS NULL
  AND strpos(reason,(d::text))>0 AND strpos(reason,((d+2)::text))>0)
  FROM public.arrangement_reviews WHERE event_request_id=saved.event_request_id),'AC3-H5: domain flags/reasons/shared actual update UUID incorrect';
 ASSERT (SELECT array_agg(arrangement_id ORDER BY arrangement_id) FROM public.arrangement_reviews WHERE event_request_id=saved.event_request_id)
  =ARRAY(SELECT x::uuid FROM unnest(ARRAY[f->>'approved',f->>'past',f->>'future']) x ORDER BY x::uuid),'AC3-H5: moved venue or linked past/future equipment omitted';
 ASSERT (SELECT count(*)=3 AND bool_and(j.published_at IS NULL AND j.payload->>'trigger_id'=r.trigger_id::text)
  FROM public.arrangement_reviews r JOIN public.arrangement_review_notification_outbox j ON j.review_id=r.id WHERE r.event_request_id=saved.event_request_id),'AC3-H5: review delivery work not atomic';
 ASSERT (SELECT count(*)=1 AND bool_and(event_updated_at=(SELECT updated_at FROM public.event_requests WHERE id=saved.event_request_id)
  AND changed_fields=ARRAY['proposed_date_times'] AND cleared_at IS NULL) FROM public.event_registration_reviews WHERE event_request_id=saved.event_request_id),'AC3-H5: registration date review missing';
 ASSERT pg_temp.date_state()-ARRAY['events','changes','bookings','reviews','review_jobs','registration_reviews']
  =before_state-ARRAY['events','changes','bookings','reviews','review_jobs','registration_reviews'],'AC3-H5: reservations, attendee state, lifecycle/history, assignments or other delivery data changed';
 ASSERT pg_temp.date_unrelated(pg_temp.date_state(),saved.event_request_id,saved.id)
  =pg_temp.date_unrelated(before_state,saved.event_request_id,saved.id),'AC3-H5: another event/proposal/review/job changed';
 -- AC5-N4 (negative): duplicate date approval cannot replace accepted ranges/audit or create a second review cause.
 before_state:=pg_temp.date_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_date_event_change_request(saved.event_request_id,saved.id,actor::varchar,NULL,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC5-N4: repeated date approval accepted' USING ERRCODE='P9904';
 EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
 ASSERT pg_temp.date_state()=before_state,'AC5-N4: repeated date approval changed protected state';

 -- AC3-H6 (happy): explicit complete ranges support changed wall times and mixed approved fields without guessing booking duration or rewriting the proposal.
 f:=pg_temp.date_fixture(); d:=(f->>'day')::date; actor:=(f->>'owner')::uuid;
 UPDATE public.event_change_requests SET proposed_changes=jsonb_build_object('proposed_date_times',jsonb_build_array((d+2)::text||'T11:00:00+08:00',(d+2)::text||'T16:00:00+08:00'),
  'expected_attendance',40,'venue_requirements','Accessible room','equipment_requirements','Two microphones','registration_needs','Online form') WHERE id=(f->>'change')::uuid;
 plan:=jsonb_build_array(jsonb_build_object('booking_id',f->>'approved','start_date',(d+2)::text,'end_date',(d+2)::text,'start_minute',900,'end_minute',1020),
  jsonb_build_object('booking_id',f->>'pending','start_date',(d+2)::text,'end_date',(d+2)::text,'start_minute',630,'end_minute',690));
 before_state:=pg_temp.date_state(); original:=(SELECT to_jsonb(r) FROM public.event_change_requests r WHERE id=(f->>'change')::uuid);
 SET LOCAL ROLE service_role;
 saved:=public.approve_date_event_change_request((f->>'event')::uuid,(f->>'change')::uuid,actor::varchar,NULL,plan);
 RESET ROLE;
 ASSERT saved.status='Approved' AND saved.proposed_changes=original->'proposed_changes' AND saved.base_event_updated_at=(original->>'base_event_updated_at')::timestamptz,'AC3-H6: mixed proposal/audit provenance lost';
 ASSERT (SELECT jsonb_agg(x ORDER BY x->>'booking_id') FROM jsonb_array_elements(saved.applied_booking_plan) x)
  =(SELECT jsonb_agg(x ORDER BY x->>'booking_id') FROM jsonb_array_elements(plan) x),'AC3-H6: exact chosen ranges not retained';
 ASSERT (SELECT proposed_date_times=ARRAY[((d+2)::text||'T11:00:00+08:00')::timestamptz,((d+2)::text||'T16:00:00+08:00')::timestamptz]
  AND expected_attendance=40 AND venue_requirements='Accessible room' AND equipment_requirements='Two microphones' AND registration_needs='Online form' AND status='Planning'
  FROM public.event_requests WHERE id=saved.event_request_id),'AC3-H6: date/mixed proposal only partially applied';
 FOR actual IN SELECT value FROM jsonb_array_elements(before_state->'bookings') LOOP
  expected:=actual;
  IF actual->>'id'=f->>'pending' THEN expected:=actual||jsonb_build_object('start_date',(d+2)::text,'end_date',(d+2)::text,'start_minute',630,'end_minute',690);
  ELSIF actual->>'id'=f->>'approved' THEN expected:=actual||jsonb_build_object('start_date',(d+2)::text,'end_date',(d+2)::text,'start_minute',900,'end_minute',1020); END IF;
  ASSERT (SELECT to_jsonb(r)=expected FROM public.venue_booking_requests r WHERE id=(actual->>'id')::uuid),'AC3-H6: explicit mapping altered IDs/status/audit/other rows or inferred a different duration';
 END LOOP;
 ASSERT (SELECT count(*)=3 AND count(DISTINCT trigger_id)=1 FROM public.arrangement_reviews WHERE event_request_id=saved.event_request_id),'AC3-H6: mixed update cause not shared across affected arrangements';
 ASSERT (SELECT count(*)=1 AND bool_and(changed_fields @> ARRAY['proposed_date_times','expected_attendance','registration_needs'] AND cardinality(changed_fields)=3)
  FROM public.event_registration_reviews WHERE event_request_id=saved.event_request_id),'AC3-H6: mixed registration review incorrect';
 ASSERT pg_temp.date_state()-ARRAY['events','changes','bookings','reviews','review_jobs','registration_reviews']
  =before_state-ARRAY['events','changes','bookings','reviews','review_jobs','registration_reviews'],'AC3-H6: unrelated protected state changed';
 ASSERT pg_temp.date_unrelated(pg_temp.date_state(),saved.event_request_id,saved.id)
  =pg_temp.date_unrelated(before_state,saved.event_request_id,saved.id),'AC3-H6: another event/proposal/review/job changed';

 -- AC4-P4/P5/P6/P7 (partition): an existing approved booking, active block, candidate pair or unavailable venue refuses the whole batch without any saved side effect.
 FOREACH mode IN ARRAY ARRAY['booking','block','pair','unavailable'] LOOP
  f:=pg_temp.date_fixture(); d:=(f->>'day')::date; actor:=(f->>'owner')::uuid; plan:=pg_temp.date_plan(f); conflict:=NULL; block_id:=NULL;
  IF mode='booking' THEN
   INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,start_minute,end_minute,status,decided_by,decided_at)
   VALUES((f->>'venue')::uuid,actor,gen_random_uuid(),d+2,d+2,600,690,'approved',actor,now()) RETURNING id INTO conflict;
  ELSIF mode='block' THEN
   INSERT INTO public.venue_blocks(venue_id,start_date,end_date,slots,reason_category,status,created_by)
   VALUES((f->>'venue')::uuid,d+2,d+2,'{AM}','maintenance','active',actor) RETURNING id INTO block_id;
  ELSIF mode='pair' THEN
   plan:=jsonb_set(plan,'{1,start_date}',to_jsonb((d+2)::text)); plan:=jsonb_set(plan,'{1,end_date}',to_jsonb((d+2)::text));
   plan:=jsonb_set(plan,'{1,start_minute}','675'); plan:=jsonb_set(plan,'{1,end_minute}','705');
  ELSE UPDATE public.venues SET status='blocked' WHERE id=(f->>'venue')::uuid; END IF;
  before_state:=pg_temp.date_state();
  BEGIN
   SET LOCAL ROLE service_role; PERFORM public.approve_date_event_change_request((f->>'event')::uuid,(f->>'change')::uuid,actor::varchar,NULL,plan); RESET ROLE;
   RAISE EXCEPTION 'AC4 partitions: conflicting date batch accepted (%)',mode USING ERRCODE='P9905';
  EXCEPTION WHEN SQLSTATE 'P0005' THEN
   GET STACKED DIAGNOSTICS detail=PG_EXCEPTION_DETAIL;
   issues:=detail::jsonb;
   ASSERT jsonb_typeof(issues)='array' AND jsonb_array_length(issues)>0,'AC4 partitions: no structured conflict evidence';
   ASSERT EXISTS(SELECT 1 FROM jsonb_array_elements(issues) x WHERE x->>'booking_id' IN(f->>'pending',f->>'approved')
    AND x->'refusal_codes' ? CASE mode WHEN 'block' THEN 'active_block' WHEN 'unavailable' THEN 'venue_unavailable' ELSE 'booking_conflict' END),
    'AC4 partitions: exact mechanism/affected booking absent';
   IF conflict IS NOT NULL THEN ASSERT EXISTS(SELECT 1 FROM jsonb_array_elements(issues) x WHERE x->'conflicting_booking_ids' ? conflict::text),'AC4-P4: conflict identity lost'; END IF;
   IF block_id IS NOT NULL THEN ASSERT EXISTS(SELECT 1 FROM jsonb_array_elements(issues) x WHERE x->'conflicting_block_ids' ? block_id::text),'AC4-P5: block identity lost'; END IF;
  END;
  ASSERT pg_temp.date_state()=before_state,'AC4 partitions: refused batch wrote plan/audit/reviews/jobs or any protected state';
 END LOOP;

 -- AC3-N24 (negative): missing, duplicate or foreign plan identities cannot silently omit, reassign or duplicate a current arrangement.
 f:=pg_temp.date_fixture(); actor:=(f->>'owner')::uuid; plan:=pg_temp.date_plan(f);
 FOREACH bad IN ARRAY ARRAY[jsonb_build_array(plan->0),jsonb_build_array(plan->0,plan->0),jsonb_set(plan,'{1,booking_id}',to_jsonb(foreign_id::text))] LOOP
  before_state:=pg_temp.date_state();
  BEGIN
   SET LOCAL ROLE service_role; PERFORM public.approve_date_event_change_request((f->>'event')::uuid,(f->>'change')::uuid,actor::varchar,NULL,bad); RESET ROLE;
   RAISE EXCEPTION 'AC3-N24: malformed complete booking set accepted' USING ERRCODE='P9923';
  EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
  ASSERT pg_temp.date_state()=before_state,'AC3-N24: malformed complete set changed state';
 END LOOP;

 -- AC3-X23 (cross-cutting): required registration-review failure rolls back already moved bookings, event changes, decision, arrangement flags and all queued work.
 f:=pg_temp.date_fixture(); actor:=(f->>'owner')::uuid; before_state:=pg_temp.date_state();
 PERFORM set_config('scrum35.date_fault_event',f->>'event',true);
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_date_event_change_request((f->>'event')::uuid,(f->>'change')::uuid,actor::varchar,NULL,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC3-X23: expected required review fault absent' USING ERRCODE='P9914';
 EXCEPTION WHEN SQLSTATE '23514' THEN
  GET STACKED DIAGNOSTICS message=MESSAGE_TEXT;
  ASSERT message='VERIFY35 required registration-review failure','AC3-X23: unrelated constraint mistaken for injected failure';
 END;
 ASSERT pg_temp.date_state()=before_state,'AC3-X23: required-work failure left partial booking/event/decision/review/job writes';
 PERFORM set_config('scrum35.date_fault_event','',true);

 -- AC2-N10 (negative): current assignment, event version and Pending status are rechecked natively before any date or arrangement write.
 FOREACH mode IN ARRAY ARRAY['assignment','stale','state','no_op'] LOOP
  f:=pg_temp.date_fixture(); actor:=(f->>'owner')::uuid;
  IF mode='assignment' THEN INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by) VALUES((f->>'event')::uuid,gen_random_uuid()::text,'verify35');
  ELSIF mode='stale' THEN UPDATE public.event_requests SET description='A newer saved detail' WHERE id=(f->>'event')::uuid;
  ELSIF mode='state' THEN UPDATE public.event_requests SET status='Confirmed' WHERE id=(f->>'event')::uuid;
  ELSE UPDATE public.event_change_requests SET proposed_changes=jsonb_build_object('proposed_date_times',(SELECT to_jsonb(proposed_date_times) FROM public.event_requests WHERE id=(f->>'event')::uuid)) WHERE id=(f->>'change')::uuid; END IF;
  before_state:=pg_temp.date_state(); plan:=pg_temp.date_plan(f);
  BEGIN
   SET LOCAL ROLE service_role; PERFORM public.approve_date_event_change_request((f->>'event')::uuid,(f->>'change')::uuid,actor::varchar,NULL,plan); RESET ROLE;
   RAISE EXCEPTION 'AC2-N10: invalid authoritative date state accepted (%)',mode USING ERRCODE='P9904';
  EXCEPTION WHEN SQLSTATE 'P0003' THEN ASSERT mode='assignment','AC2-N10: wrong assignment error partition';
   WHEN SQLSTATE 'P0004' THEN ASSERT mode<>'assignment','AC2-N10: assignment collapsed into stale refusal'; END;
  ASSERT pg_temp.date_state()=before_state,'AC2-N10: refused authoritative state changed protected data';
 END LOOP;

 -- AC3-X24 (cross-cutting): browser callers cannot invoke the atomic date writer, and direct service INSERT/DELETE membership bypasses stay denied.
 ASSERT NOT has_table_privilege('service_role','public.venue_booking_requests','INSERT') AND NOT has_table_privilege('service_role','public.venue_booking_requests','DELETE'), 'AC3-X24: membership bypass reopened';
 FOREACH browser IN ARRAY ARRAY['anon','authenticated'] LOOP
  ASSERT NOT has_function_privilege(browser,'public.approve_date_event_change_request(uuid,uuid,character varying,text,jsonb)','EXECUTE'),'AC3-X24: browser date-writer privilege';
  before_state:=pg_temp.date_state();
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',browser);
   PERFORM public.approve_date_event_change_request((f->>'event')::uuid,(f->>'change')::uuid,actor::varchar,NULL,NULL);
   RAISE EXCEPTION 'AC3-X24: browser executed date writer' USING ERRCODE='P9925';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  ASSERT pg_temp.date_state()=before_state,'AC3-X24: refused browser changed protected data';
 END LOOP;
 RAISE NOTICE 'SCRUM35 date approval native verification PASSED';
END $cases$;
ROLLBACK;
