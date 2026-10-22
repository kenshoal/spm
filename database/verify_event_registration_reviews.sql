-- SCRUM-35 registration-review increment: owned disposable PostgreSQL only.
-- The initial production-owned table scaffold allows a real UPDATE -> missing-review Red.
-- No Auth/API delivery claim; temporary fault injection is forbidden on shared infrastructure.
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
 ASSERT to_regclass('public.event_registration_reviews') IS NOT NULL,
  'SETUP: reviewed registration-review table scaffold required before behaviour assertions';
END $$;
CREATE FUNCTION pg_temp.registration_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
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
 'safety',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.safety_reviews x),
 'submission_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_outbox x),
 'inbox',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.notifications x));
$$;
CREATE FUNCTION pg_temp.registration_write_fault() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.event_request_id::text=current_setting('scrum35.registration_fault_event',true) THEN
  RAISE EXCEPTION 'VERIFY35 injected registration review failure' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER verify35_registration_fault BEFORE INSERT ON public.event_registration_reviews
 FOR EACH ROW EXECUTE FUNCTION pg_temp.registration_write_fault();
DO $cases$
DECLARE
 owner_id uuid; other_actor uuid:=gen_random_uuid(); e uuid:=gen_random_uuid(); a uuid:=gen_random_uuid();
 gate uuid:=gen_random_uuid(); confirmed uuid:=gen_random_uuid(); draft uuid:=gen_random_uuid();
 venue uuid:=gen_random_uuid(); older uuid; newer uuid; gate_review uuid; cid uuid;
 row_before jsonb; proposal_before jsonb; before_state jsonb; after_state jsonb; expected jsonb; before_event jsonb;
 acknowledged public.event_registration_reviews; saved public.event_change_requests;
 fields text[]; started timestamptz; refusal text; v_detail text; browser text;
 today date:=(transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
BEGIN
 SELECT id INTO owner_id FROM auth.users ORDER BY id LIMIT 1;
 ASSERT owner_id IS NOT NULL, 'SETUP: existing disposable Auth fixture required';
 INSERT INTO public.event_requests(id,organiser_id,status,event_name,expected_attendance,registration_needs,proposed_date_times,
  registration_capacity,registration_opens_at,registration_closes_at)
 VALUES(e,owner_id,'Planning','VERIFY35 registration causes',25,'Paper form',ARRAY['2030-01-10T10:00:00+08:00'::timestamptz],80,now()-interval '1 day',now()+interval '1 day'),
       (a,owner_id,'Planning','VERIFY35 registration approval',25,'Paper form','{}',80,now()-interval '1 day',now()+interval '1 day'),
       (gate,owner_id,'Planning','VERIFY35 registration gates',25,'Paper form','{}',80,now()-interval '1 day',now()+interval '1 day'),
       (confirmed,owner_id,'Confirmed','VERIFY35 retained attendee',25,'Existing form','{}',80,now()-interval '1 day',now()+interval '1 day'),
       (draft,owner_id,'Draft','VERIFY35 excluded draft',25,'Paper form','{}',80,now()-interval '1 day',now()+interval '1 day');
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
 VALUES(e,owner_id::text,'verify35'),(a,owner_id::text,'verify35'),(gate,owner_id::text,'verify35');
 INSERT INTO public.staff_roles(user_id,role) VALUES(owner_id,'safety_officer') ON CONFLICT DO NOTHING;
 SET LOCAL ROLE service_role;
 PERFORM public.register_for_event(confirmed,owner_id,clock_timestamp());
 RESET ROLE;

 -- AC3-X17 (cross-cutting): one significant event version produces complete before/after evidence, and later real causes retain older rows.
 UPDATE public.event_requests SET expected_attendance=40,registration_needs='Accessible online form' WHERE id=e;
 ASSERT (SELECT count(*)=1 FROM public.event_registration_reviews WHERE event_request_id=e),
  'AC3-X17: significant event update did not persist exactly one registration review';
 SELECT id,changed_fields,to_jsonb(r) INTO older,fields,row_before FROM public.event_registration_reviews r WHERE event_request_id=e;
 ASSERT fields @> ARRAY['expected_attendance','registration_needs'] AND cardinality(fields)=2
  AND (SELECT event_updated_at=(SELECT updated_at FROM public.event_requests WHERE id=e)
   AND strpos(reason,'25')>0 AND strpos(reason,'40')>0 AND strpos(reason,'Paper form')>0
   AND strpos(reason,'Accessible online form')>0 AND cleared_at IS NULL AND cleared_by IS NULL
   FROM public.event_registration_reviews WHERE id=older), 'AC3-X17: cause/version/evidence/audit incorrect';
 UPDATE public.event_requests SET proposed_date_times=ARRAY['2030-01-12T10:00:00+08:00'::timestamptz] WHERE id=e;
 SELECT id INTO newer FROM public.event_registration_reviews WHERE event_request_id=e AND id<>older;
 ASSERT newer IS NOT NULL AND (SELECT count(*)=2 FROM public.event_registration_reviews WHERE event_request_id=e)
  AND (SELECT changed_fields=ARRAY['proposed_date_times'] AND strpos(reason,'2030-01-10')>0 AND strpos(reason,'2030-01-12')>0
   FROM public.event_registration_reviews WHERE id=newer), 'AC3-X17: later date cause missing or incorrectly attributed';
 ASSERT (SELECT to_jsonb(r)=row_before FROM public.event_registration_reviews r WHERE id=older), 'AC3-X17: later edit rewrote older evidence';
 before_state:=pg_temp.registration_state();
 UPDATE public.event_requests SET expected_attendance=40,registration_needs='  Accessible online form  ',
  venue_requirements='Changed venue-only text',equipment_requirements='Changed equipment-only text' WHERE id=e;
 UPDATE public.event_requests SET expected_attendance=40,registration_needs='Changed draft form' WHERE id=draft;
 UPDATE public.event_requests SET status='Completed' WHERE id=draft;
 UPDATE public.event_requests SET expected_attendance=60,registration_needs='Changed completed form' WHERE id=draft;
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_registration_reviews r)=before_state->'registration_reviews',
  'AC3-X17: no-op/unrelated/terminal edits raised or cleared registration reviews';

 -- AC3-H4 (happy): requirements-text approval saves plan/audit/review atomically without touching attendee state, registration settings or other arrangements.
 SELECT id INTO cid FROM public.create_event_change_request(a,owner_id,'Use the accessible online form',
  '{"registration_needs":"Accessible online form"}');
 before_state:=pg_temp.registration_state();
 before_event:=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=a);
 proposal_before:=(SELECT to_jsonb(r) FROM public.event_change_requests r WHERE id=cid);
 started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 saved:=public.approve_non_date_event_change_request(a,cid,owner_id::text,NULL);
 RESET ROLE;
 ASSERT saved.status='Approved' AND saved.coordinator_id=owner_id::text AND saved.decision_reason IS NULL
  AND saved.decided_at BETWEEN started AND clock_timestamp(), 'AC3-H4: registration approval audit missing';
 expected:=before_event||jsonb_build_object('registration_needs','Accessible online form','updated_at',(SELECT updated_at FROM public.event_requests WHERE id=a));
 ASSERT (SELECT to_jsonb(r)=expected AND updated_at>saved.base_event_updated_at FROM public.event_requests r WHERE id=a),
  'AC3-H4: approval changed fields beyond requirements text/version';
 ASSERT to_jsonb(saved)-ARRAY['status','coordinator_id','decision_reason','decided_at']
  =proposal_before-ARRAY['status','coordinator_id','decision_reason','decided_at'], 'AC3-H4: original proposal/provenance changed';
 ASSERT (SELECT to_jsonb(r)=to_jsonb(saved) FROM public.event_change_requests r WHERE id=cid), 'AC3-H4: returned decision not stored';
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_requests r WHERE id<>a)
  =(SELECT coalesce(jsonb_agg(r ORDER BY r->>'id'),'[]') FROM jsonb_array_elements(before_state->'events') r WHERE r->>'id'<>a::text),
  'AC3-H4: approval rewrote another event';
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_change_requests r WHERE id<>cid)
  =(SELECT coalesce(jsonb_agg(r ORDER BY r->>'id'),'[]') FROM jsonb_array_elements(before_state->'changes') r WHERE r->>'id'<>cid::text),
  'AC3-H4: approval rewrote another proposal';
 ASSERT (SELECT count(*)=1 AND bool_and(changed_fields=ARRAY['registration_needs']
  AND event_updated_at=(SELECT updated_at FROM public.event_requests WHERE id=a)
  AND strpos(reason,'Paper form')>0 AND strpos(reason,'Accessible online form')>0)
  FROM public.event_registration_reviews WHERE event_request_id=a), 'AC3-H4: atomic registration review evidence missing';
 ASSERT pg_temp.registration_state()-ARRAY['events','changes','registration_reviews']=before_state-ARRAY['events','changes','registration_reviews'],
  'AC3-H4: registration approval touched attendees/settings-related records/resources/lifecycle/notification work';

 -- AC3-X21 (cross-cutting): a failed required review INSERT rolls back the actual approval/event/audit, not a test substitute.
 SELECT id INTO cid FROM public.create_event_change_request(a,owner_id,'Another accessible form',
  '{"registration_needs":"Another accessible form"}');
 PERFORM set_config('scrum35.registration_fault_event',a::text,true);
 before_state:=pg_temp.registration_state();
 BEGIN
  SET LOCAL ROLE service_role;
  PERFORM public.approve_non_date_event_change_request(a,cid,owner_id::text,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC3-X21: required registration review failure not reached' USING ERRCODE='P9935';
 EXCEPTION WHEN check_violation THEN
  ASSERT SQLERRM='VERIFY35 injected registration review failure', 'AC3-X21: wrong injected failure';
 END;
 ASSERT pg_temp.registration_state()=before_state, 'AC3-X21: failed registration review left partial plan/decision/state';
 PERFORM set_config('scrum35.registration_fault_event','',true);

 -- AC3-X19 (cross-cutting): exact older acknowledgement retains immutable evidence and every newer outstanding cause.
 before_state:=pg_temp.registration_state(); started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 acknowledged:=public.acknowledge_event_registration_review(e,older,owner_id);
 RESET ROLE;
 ASSERT acknowledged.id=older AND acknowledged.cleared_by=owner_id AND acknowledged.cleared_at BETWEEN started AND clock_timestamp()
  AND to_jsonb(acknowledged)-ARRAY['cleared_at','cleared_by']=row_before-ARRAY['cleared_at','cleared_by'], 'AC3-X19: exact audit/evidence incorrect';
 expected:=before_state||jsonb_build_object('registration_reviews',(
  SELECT jsonb_agg(CASE WHEN x->>'id'=older::text THEN to_jsonb(acknowledged) ELSE x END ORDER BY x->>'id')
  FROM jsonb_array_elements(before_state->'registration_reviews') x));
 ASSERT pg_temp.registration_state()=expected, 'AC3-X19: acknowledgement changed newer review or unrelated state';

 -- AC3-N20/AC3-N21/AC3-N22 (negative): unknown scope, current reassignment and repetition are authoritative and leave complete state unchanged.
 FOREACH refusal IN ARRAY ARRAY['repeat','scope','reassigned'] LOOP
  IF refusal='reassigned' THEN
   INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by) VALUES(e,other_actor::text,'verify35');
  END IF;
  before_state:=pg_temp.registration_state();
  BEGIN
   SET LOCAL ROLE service_role;
   PERFORM public.acknowledge_event_registration_review(CASE WHEN refusal='scope' THEN a ELSE e END,older,owner_id);
   RESET ROLE;
   RAISE EXCEPTION 'AC3-N20/21/22: refused acknowledgement accepted (%)',refusal USING ERRCODE='P9936';
  EXCEPTION WHEN SQLSTATE 'P0004' THEN IF refusal<>'repeat' THEN RAISE; END IF;
   WHEN SQLSTATE 'P0002' THEN IF refusal<>'scope' THEN RAISE; END IF;
   WHEN SQLSTATE 'P0003' THEN IF refusal<>'reassigned' THEN RAISE; END IF;
  END;
  ASSERT pg_temp.registration_state()=before_state, 'AC3-N20/21/22: refusal mutated protected state';
 END LOOP;

 -- AC4-X5 (cross-cutting): actual handover and safety approval consume the same outstanding registration facts and cannot confirm before acknowledgement.
 ASSERT private.event_readiness_issues(gate)='[{"kind":"no_venue_booking"}]'::jsonb,
  'AC4-X5: ordinary missing-venue readiness was changed';
 INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES(venue,'VERIFY35 registration gate venue','Test wing',100,'{}','{}','{theatre}','{AM}');
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,start_minute,end_minute,status,decided_by,decided_at)
 VALUES(venue,owner_id,gate,today+20,today+20,'{AM}',600,720,'approved',owner_id,clock_timestamp());
 ASSERT private.event_readiness_issues(gate)='[]'::jsonb, 'SETUP: ordinary venue/equipment readiness required';
 UPDATE public.event_requests SET registration_needs='Checked online form' WHERE id=gate;
 SELECT id INTO gate_review FROM public.event_registration_reviews WHERE event_request_id=gate;
 ASSERT private.event_readiness_issues(gate)=jsonb_build_array(jsonb_build_object('kind','arrangement_needs_review',
  'arrangement','registration','review_id',gate_review,'reason',(SELECT reason FROM public.event_registration_reviews WHERE id=gate_review))),
  'AC4-X5: shared readiness omitted/changed registration evidence';
 before_state:=pg_temp.registration_state();
 BEGIN
  SET LOCAL ROLE service_role;
  PERFORM public.send_event_request_for_safety_review(gate,owner_id::text); RESET ROLE;
  RAISE EXCEPTION 'AC4-X5: handover accepted outstanding registration review' USING ERRCODE='P9937';
 EXCEPTION WHEN SQLSTATE 'P0005' THEN
  GET STACKED DIAGNOSTICS v_detail=PG_EXCEPTION_DETAIL;
  ASSERT v_detail::jsonb=private.event_readiness_issues(gate), 'AC4-X5: handover lost useful registration detail';
 END;
 ASSERT pg_temp.registration_state()=before_state, 'AC4-X5: refused handover changed state';
 UPDATE public.event_requests SET status='Safety Review' WHERE id=gate;
 before_state:=pg_temp.registration_state();
 BEGIN
  SET LOCAL ROLE service_role;
  PERFORM public.decide_safety_review(gate,owner_id,'approved',NULL,'[]'); RESET ROLE;
  RAISE EXCEPTION 'AC4-X5: safety approval accepted outstanding registration review' USING ERRCODE='P9938';
 EXCEPTION WHEN SQLSTATE 'P0005' THEN
  GET STACKED DIAGNOSTICS v_detail=PG_EXCEPTION_DETAIL;
  ASSERT v_detail::jsonb=private.event_readiness_issues(gate), 'AC4-X5: safety approval lost useful registration detail';
 END;
 ASSERT pg_temp.registration_state()=before_state, 'AC4-X5: refused safety approval changed state';
 SET LOCAL ROLE service_role;
 PERFORM public.acknowledge_event_registration_review(gate,gate_review,owner_id);
 RESET ROLE;
 ASSERT private.event_readiness_issues(gate)='[]'::jsonb, 'AC4-X5: acknowledged registration still blocks otherwise-ready event';
 SET LOCAL ROLE service_role;
 PERFORM public.decide_safety_review(gate,owner_id,'approved',NULL,'[]');
 RESET ROLE;
 ASSERT (SELECT status='Confirmed' FROM public.event_requests WHERE id=gate), 'AC4-X5: actual safety approval remained blocked after acknowledgement';
 UPDATE public.event_requests SET status='Planning' WHERE id=gate;
 SET LOCAL ROLE service_role;
 PERFORM public.send_event_request_for_safety_review(gate,owner_id::text);
 RESET ROLE;
 ASSERT (SELECT status='Safety Review' FROM public.event_requests WHERE id=gate), 'AC4-X5: actual handover remained blocked after acknowledgement';

 -- AC3-X19 (cross-cutting): browser callers and direct table writes cannot bypass the audited acknowledgement boundary.
 ASSERT (SELECT relrowsecurity FROM pg_class WHERE oid='public.event_registration_reviews'::regclass),
  'AC3-X19: registration-review RLS disabled';
 ASSERT has_table_privilege('service_role','public.event_registration_reviews','SELECT')
  AND NOT has_table_privilege('service_role','public.event_registration_reviews','INSERT,UPDATE,DELETE'),
  'AC3-X19: service review table privileges widened';
 FOREACH browser IN ARRAY ARRAY['anon','authenticated'] LOOP
  ASSERT NOT has_table_privilege(browser,'public.event_registration_reviews','SELECT,INSERT,UPDATE,DELETE')
   AND NOT has_function_privilege(browser,'public.acknowledge_event_registration_review(uuid,uuid,uuid)','EXECUTE'),
   'AC3-X19: browser review boundary exposed';
  before_state:=pg_temp.registration_state();
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',browser);
   PERFORM public.acknowledge_event_registration_review(gate,gate_review,owner_id); RESET ROLE;
   RAISE EXCEPTION 'AC3-X19: browser acknowledgement executed' USING ERRCODE='P9939';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  ASSERT pg_temp.registration_state()=before_state, 'AC3-X19: browser refusal changed state';
 END LOOP;
 ASSERT (SELECT count(*)=1 AND bool_and(status='Registered') FROM public.event_registrations WHERE event_request_id=confirmed),
  'AC3-H4: retained attendee registration changed';
 RAISE NOTICE 'SCRUM35 registration review verification PASSED';
END $cases$;
ROLLBACK;
