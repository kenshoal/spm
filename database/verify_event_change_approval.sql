-- SCRUM35 accepted non-date approval: actual RPC/64 writers, isolated rollback verification only.
-- HTTP behaviour Red is separate; an absent0053 RPC is a setup precondition, never feature Red.
BEGIN;
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
 ASSERT to_regprocedure('public.approve_non_date_event_change_request(uuid,uuid,character varying,text)') IS NOT NULL,
  'SETUP: frozen non-date approval RPC must be applied before native verification';
END $$;
CREATE FUNCTION pg_temp.scrum35_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_requests x),
 'history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_status_history x),
 'changes',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_change_requests x),
 'assignments',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_coordinator_assignments x),
 'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_booking_requests x),
 'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment x),
 'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_requirements x),
 'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_reservations x),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.arrangement_reviews x),
 'review_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x),
 'submission_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_outbox x),
 'inbox',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.notifications x));
$$;

CREATE TEMP SEQUENCE scrum35_approval_fault_count;
CREATE FUNCTION pg_temp.scrum35_approval_fault() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 -- Advance only for the explicitly activated event: NULL AND expressions can otherwise consume sequence values.
 IF NEW.event_request_id::text=current_setting('scrum35.approval_fault_event',true) THEN
  IF nextval('pg_temp.scrum35_approval_fault_count')=2 THEN
   RAISE EXCEPTION 'SCRUM35 injected second approval flag failure' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER scrum35_approval_fault BEFORE INSERT ON public.arrangement_reviews
 FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum35_approval_fault();
DO $case$
DECLARE
 owner_id uuid; e uuid; p uuid; other uuid; venue uuid; booking uuid; equipment uuid; requirement uuid; reservation uuid;
 change public.event_change_requests; pending public.event_change_requests; saved public.event_change_requests;
 current_actor varchar := '35000000-0000-4000-8000-000000000001';
 former_actor varchar := '35000000-0000-4000-8000-000000000002';
 invalid_actor varchar; payload jsonb; bad jsonb; before_state jsonb; before_event jsonb; expected jsonb; original jsonb;
 started timestamptz; message text; v_role text;
 today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
BEGIN
 SELECT id INTO owner_id FROM auth.users ORDER BY created_at LIMIT 1;
 ASSERT owner_id IS NOT NULL,'SETUP: existing disposable Auth FK identity required';
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance,venue_requirements,equipment_requirements)
 VALUES(owner_id,'VERIFY35 non-date approval','Approved',25,'Seminar room','Microphone') RETURNING id INTO e;
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance,venue_requirements,equipment_requirements)
 VALUES(owner_id,'VERIFY35 Planning approval guards','Planning',25,'Seminar room','Microphone') RETURNING id INTO p;
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(owner_id,'VERIFY35 other event','Approved',25) RETURNING id INTO other;
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
 VALUES(e,former_actor,'verify'),(e,current_actor,'verify'),(p,current_actor,'verify'),(other,current_actor,'verify');
 INSERT INTO public.venues(name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES('VERIFY35 approval venue','Test wing',100,'{}','{}','{theatre}','{AM}') RETURNING id INTO venue;
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
 VALUES(venue,owner_id,e,today+30,today+30,'{AM}','approved',owner_id,now()) RETURNING id INTO booking;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('VERIFY35 approval microphone',10,'Test store',owner_id) RETURNING id INTO equipment;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(e,'VERIFY35 approval microphone',2,owner_id) RETURNING id INTO requirement;
 INSERT INTO public.equipment_reservations(equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(equipment,requirement,e,1,today+30,today+30,owner_id) RETURNING id INTO reservation;
 payload:='{"expected_attendance":80,"venue_requirements":"Auditorium","equipment_requirements":"Projector"}'::jsonb;
 SELECT * INTO change FROM public.create_event_change_request(e,owner_id,'Agreed non-date plan update',payload);
 before_state:=pg_temp.scrum35_state(); before_event:=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=e); original:=to_jsonb(change);

 -- AC3-H1 (happy): apply only the exact accepted fields with durable decision and both affected domain flags in one native transaction.
 started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 saved:=public.approve_non_date_event_change_request(e,change.id,current_actor,NULL);
 RESET ROLE;
 ASSERT saved.status='Approved' AND saved.coordinator_id=current_actor AND saved.decision_reason IS NULL
  AND saved.decided_at BETWEEN started AND clock_timestamp(),'AC3-H1: complete approval audit missing';
 ASSERT to_jsonb(saved)-ARRAY['status','coordinator_id','decision_reason','decided_at']=original-ARRAY['status','coordinator_id','decision_reason','decided_at'],
  'AC3-H1: original proposal identity/value/provenance changed';
 expected:=before_event||payload||jsonb_build_object('updated_at',(SELECT updated_at FROM public.event_requests WHERE id=e));
 ASSERT (SELECT to_jsonb(r)=expected AND updated_at>change.base_event_updated_at FROM public.event_requests r WHERE id=e),
  'AC3-H1: proposed values/version not applied exactly or unrelated event fields changed';
 ASSERT (SELECT to_jsonb(r)=to_jsonb(saved) FROM public.event_change_requests r WHERE id=change.id),'AC3-H1: returned audit not stored';
 ASSERT (SELECT count(*)=2 AND count(DISTINCT trigger_id)=1 AND bool_and(trigger_type='event_change' AND cleared_at IS NULL
   AND strpos(reason,'25')>0 AND strpos(reason,'80')>0) FROM public.arrangement_reviews WHERE event_request_id=e),
  'AC3-H1: affected arrangements missing their shared update cause/reason';
 ASSERT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=e AND arrangement='venue_booking' AND arrangement_id=booking
  AND changed_fields @> ARRAY['expected_attendance','venue_requirements'] AND cardinality(changed_fields)=2 AND strpos(reason,'Seminar room')>0 AND strpos(reason,'Auditorium')>0)
  AND EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=e AND arrangement='equipment_reservation' AND arrangement_id=reservation
  AND changed_fields @> ARRAY['expected_attendance','equipment_requirements'] AND cardinality(changed_fields)=2 AND strpos(reason,'Microphone')>0 AND strpos(reason,'Projector')>0),
  'AC3-H1: domain-specific changed fields/reasons/targets incorrect';
 ASSERT (SELECT count(*)=2 AND bool_and(j.published_at IS NULL AND j.payload->>'trigger_id'=r.trigger_id::text)
  FROM public.arrangement_reviews r JOIN public.arrangement_review_notification_outbox j ON j.review_id=r.id WHERE r.event_request_id=e),
  'AC3-H1: atomic64 delivery work missing or cause mismatched';
 ASSERT pg_temp.scrum35_state()-ARRAY['events','changes','reviews','review_jobs']=before_state-ARRAY['events','changes','reviews','review_jobs'],
  'AC3-H1: approval changed assignments, arrangements, lifecycle history, inbox or submission work';
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_requests r WHERE id<>e)
  =(SELECT coalesce(jsonb_agg(r ORDER BY r->>'id'),'[]') FROM jsonb_array_elements(before_state->'events') r WHERE r->>'id'<>e::text),
  'AC3-H1: unrelated event changed';

 -- AC5-N4 (negative): a repeated approval cannot replace audit or add another significant-change cause/job.
 before_state:=pg_temp.scrum35_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(e,change.id,current_actor,'Replacement note'); RESET ROLE;
  RAISE EXCEPTION 'AC5-N4: repeated approval accepted' USING ERRCODE='P9904';
 EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state,'AC5-N4: repeated approval changed protected state';

 -- AC3-P1 (partition): Planning accepts the same non-date contract even when no existing arrangement requires a new review.
 SELECT * INTO pending FROM public.create_event_change_request(p,owner_id,'Planning non-date update','{"expected_attendance":40}');
 SET LOCAL ROLE service_role; saved:=public.approve_non_date_event_change_request(p,pending.id,current_actor,NULL); RESET ROLE;
 ASSERT saved.status='Approved' AND (SELECT expected_attendance=40 AND status='Planning' FROM public.event_requests WHERE id=p)
  AND NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=p),'AC3-P1: Planning approval or empty affected set incorrect';
 SELECT * INTO pending FROM public.create_event_change_request(p,owner_id,'Guard fixture still Pending','{"expected_attendance":60}');

 -- AC5-N3 (negative): older or null assignee cannot approve a currently assigned proposal.
 FOREACH invalid_actor IN ARRAY ARRAY[former_actor,NULL::varchar] LOOP
  before_state:=pg_temp.scrum35_state();
  BEGIN
   SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(p,pending.id,invalid_actor,NULL); RESET ROLE;
   RAISE EXCEPTION 'AC5-N3: invalid current assignee accepted' USING ERRCODE='P9903';
  EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
  ASSERT pg_temp.scrum35_state()=before_state,'AC5-N3: refused assignee changed state';
 END LOOP;

 -- AC6-N1 (negative): an older base version cannot overwrite a newer event plan.
 UPDATE public.event_requests SET description='New unrelated saved event detail' WHERE id=p;
 before_state:=pg_temp.scrum35_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(p,pending.id,current_actor,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC6-N1: stale approval accepted' USING ERRCODE='P9904';
 EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state,'AC6-N1: stale approval changed protected state';
 -- Reset only this test fixture's base version so later guards are tested independently of staleness.
 UPDATE public.event_change_requests SET base_event_updated_at=(SELECT updated_at FROM public.event_requests WHERE id=p) WHERE id=pending.id;

 -- AC2-N2 (negative): date-only, mixed-date and registration-setting proposals remain wholly unavailable at the native boundary.
 FOREACH bad IN ARRAY ARRAY['{"proposed_date_times":["2026-12-01T02:00:00Z"]}'::jsonb,
  '{"expected_attendance":60,"proposed_date_times":["2026-12-01T02:00:00Z"]}'::jsonb,'{"registration_capacity":99}'::jsonb] LOOP
  UPDATE public.event_change_requests SET proposed_changes=bad WHERE id=pending.id;
  before_state:=pg_temp.scrum35_state();
  BEGIN
   SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(p,pending.id,current_actor,NULL); RESET ROLE;
   RAISE EXCEPTION 'AC2-N2: excluded proposal was applied' USING ERRCODE='P9904';
  EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
  ASSERT pg_temp.scrum35_state()=before_state,'AC2-N2: excluded proposal partially changed state';
 END LOOP;

 -- AC3-N1 (negative): invalid stored attendance/text cannot bypass the existing positive-integer and nonblank 1..2000-character field contract.
 FOREACH bad IN ARRAY ARRAY['{"expected_attendance":null}'::jsonb,'{"expected_attendance":0}'::jsonb,
  '{"expected_attendance":40.5}'::jsonb,'{"expected_attendance":2147483648}'::jsonb,
  '{"venue_requirements":null}'::jsonb,'{"equipment_requirements":123}'::jsonb,
  jsonb_build_object('venue_requirements',E'\t\n'),jsonb_build_object('equipment_requirements',repeat('x',2001))] LOOP
  UPDATE public.event_change_requests SET proposed_changes=bad WHERE id=pending.id;
  before_state:=pg_temp.scrum35_state();
  BEGIN
   SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(p,pending.id,current_actor,NULL); RESET ROLE;
   RAISE EXCEPTION 'AC3-N1: malformed stored field accepted' USING ERRCODE='P9904';
  EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
  ASSERT pg_temp.scrum35_state()=before_state,'AC3-N1: malformed stored field partially changed state';
 END LOOP;

 -- AC3-N2 (negative): a syntactically valid no-op proposal cannot acquire an approval audit or raise work.
 UPDATE public.event_change_requests SET proposed_changes='{"expected_attendance":40}'::jsonb WHERE id=pending.id;
 before_state:=pg_temp.scrum35_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(p,pending.id,current_actor,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC3-N2: no-op proposal approved' USING ERRCODE='P9904';
 EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state,'AC3-N2: no-op approval changed state';

 -- AC3-N3 (negative): current source state is checked independently of matching base version.
 UPDATE public.event_requests SET status='Confirmed' WHERE id=p;
 UPDATE public.event_change_requests SET proposed_changes='{"expected_attendance":60}'::jsonb,
  base_event_updated_at=(SELECT updated_at FROM public.event_requests WHERE id=p) WHERE id=pending.id;
 before_state:=pg_temp.scrum35_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(p,pending.id,current_actor,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC3-N3: ineligible current state approved' USING ERRCODE='P9904';
 EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state,'AC3-N3: ineligible approval changed state';

 -- AC3-N4 (negative): a cross-event proposal cannot be approved through another event identity.
 before_state:=pg_temp.scrum35_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(other,pending.id,current_actor,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC3-N4: cross-event proposal approved' USING ERRCODE='P9902';
 EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state,'AC3-N4: mismatched event changed state';

 -- AC3-X2 (cross-cutting): failure raising the second review rolls back event, decision, first flag and any first job atomically.
 SELECT * INTO change FROM public.create_event_change_request(e,owner_id,'Atomic second accepted change','{"expected_attendance":90}');
 ASSERT NOT (SELECT is_called FROM pg_temp.scrum35_approval_fault_count),
  'AC3-X2: fault counter consumed before activation';
 PERFORM set_config('scrum35.approval_fault_event',e::text,true);
 before_state:=pg_temp.scrum35_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(e,change.id,current_actor,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC3-X2: expected second flag failure' USING ERRCODE='P9904';
 EXCEPTION WHEN SQLSTATE '23514' THEN
  GET STACKED DIAGNOSTICS message=MESSAGE_TEXT;
  ASSERT message='SCRUM35 injected second approval flag failure','AC3-X2: caught unrelated constraint';
 END;
 ASSERT pg_temp.scrum35_state()=before_state,'AC3-X2: failed flag left partial approval/plan/review/job state';

 -- AC3-X1 (cross-cutting): approval RPC remains service-only and browser execution cannot bypass API actor checks.
 ASSERT has_function_privilege('service_role','public.approve_non_date_event_change_request(uuid,uuid,character varying,text)','EXECUTE')
  AND NOT has_function_privilege('anon','public.approve_non_date_event_change_request(uuid,uuid,character varying,text)','EXECUTE')
  AND NOT has_function_privilege('authenticated','public.approve_non_date_event_change_request(uuid,uuid,character varying,text)','EXECUTE'),
  'AC3-X1: approval RPC grants incorrect';
 before_state:=pg_temp.scrum35_state();
 BEGIN
  SET LOCAL ROLE authenticated; PERFORM public.approve_non_date_event_change_request(e,change.id,current_actor,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC3-X1: browser executed approval RPC' USING ERRCODE='P9925';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state,'AC3-X1: refused browser changed state';
 RAISE NOTICE 'SCRUM35 non-date approval native verification PASSED';
END $case$;
ROLLBACK;
