-- SCRUM-35 deployment smoke, 22 October 2026. Reuses approved AC3/AC4/AC5 oracles.
-- Run only after explicit shared-verification approval and 0049 + 0053 deployment.
-- No DDL, fault injection, Auth changes, grants, external HTTP or committed fixtures.
-- Native audit sequences may consume values despite ROLLBACK; never reset them.
-- SQL service-role mechanism proof, not authenticated API/inbox or injected-failure proof.
BEGIN;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '20s';
DO $smoke$
DECLARE
 owner_id uuid; actor varchar; wrong_actor varchar := gen_random_uuid()::text;
 e uuid := gen_random_uuid(); v uuid := gen_random_uuid(); b uuid := gen_random_uuid();
 eq uuid := gen_random_uuid(); req uuid := gen_random_uuid(); res uuid := gen_random_uuid();
 cid uuid := gen_random_uuid(); later_cid uuid := gen_random_uuid();
 saved public.event_change_requests; original jsonb; before_state jsonb; after_state jsonb;
 before_event jsonb; expected_event jsonb; started timestamptz; mode text; role_name text;
 today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
 payload jsonb := '{"expected_attendance":80,"venue_requirements":"Auditorium","equipment_requirements":"Projector"}';
 snapshot_sql constant text := $snapshot$
 SELECT jsonb_build_object(
  'events',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_requests x WHERE id=$1),
  'changes',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_change_requests x WHERE event_request_id=$1),
  'assignments',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_coordinator_assignments x WHERE event_request_id=$1),
  'history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_status_history x WHERE event_request_id=$1),
  'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_booking_requests x WHERE event_request_id=$1),
  'venues',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venues x WHERE id=$3),
  'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment x WHERE id=$2),
  'equipment_history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_status_history x WHERE equipment_id=$2),
  'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_requirements x WHERE event_request_id=$1),
  'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.equipment_reservations x WHERE event_request_id=$1),
  'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.arrangement_reviews x WHERE event_request_id=$1),
  'review_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x WHERE event_request_id=$1),
  'submission_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_outbox x WHERE event_request_id=$1),
  'inbox',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.notifications x WHERE payload->>'event_request_id'=$1::text))
 $snapshot$;
BEGIN
 ASSERT current_user='postgres', 'SETUP: owner fixture context required';
 ASSERT to_regprocedure('public.reject_event_change_request(uuid,uuid,character varying,text)') IS NOT NULL
  AND to_regprocedure('public.approve_non_date_event_change_request(uuid,uuid,character varying,text)') IS NOT NULL,
  'SETUP: both reviewed deployment functions required';
 ASSERT NOT EXISTS(SELECT 1 FROM public.event_coordinator_assignments WHERE id=-350022001),
  'SETUP: reserved negative assignment ID already exists; abort without touching it';
 SELECT id INTO owner_id FROM auth.users ORDER BY id LIMIT 1;
 SELECT u.id::text INTO actor FROM auth.users u JOIN public.staff_roles r ON r.user_id=u.id
  WHERE r.role='event_coordinator' ORDER BY u.id LIMIT 1;
 ASSERT owner_id IS NOT NULL AND actor IS NOT NULL, 'SETUP: existing Auth FK identity and coordinator account required; create neither';
 ASSERT NOT EXISTS(SELECT 1 FROM public.event_requests WHERE id=e)
  AND NOT EXISTS(SELECT 1 FROM public.venues WHERE id=v)
  AND NOT EXISTS(SELECT 1 FROM public.venue_booking_requests WHERE id=b)
  AND NOT EXISTS(SELECT 1 FROM public.equipment WHERE id=eq)
  AND NOT EXISTS(SELECT 1 FROM public.equipment_requirements WHERE id=req)
  AND NOT EXISTS(SELECT 1 FROM public.equipment_reservations WHERE id=res)
  AND NOT EXISTS(SELECT 1 FROM public.event_change_requests WHERE id IN(cid,later_cid)),
  'SETUP: generated fixture identity collision';
 INSERT INTO public.event_requests(id,organiser_id,event_name,status,expected_attendance,venue_requirements,equipment_requirements)
 VALUES(e,owner_id,'VERIFY35 SHARED ROLLBACK 20261022','Planning',25,'Seminar room','Microphone');
 INSERT INTO public.event_coordinator_assignments(id,event_request_id,coordinator_id,assigned_by)
 VALUES(-350022001,e,actor,'verify35-rollback');
 INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES(v,'VERIFY35 SHARED ROLLBACK 20261022','Isolated verification fixture',100,'{}','{}','{theatre}','{AM}');
 INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,slots,start_minute,end_minute,status,decided_by,decided_at)
 VALUES(b,v,owner_id,e,today+30,today+30,'{AM}',600,720,'approved',owner_id,clock_timestamp());
 INSERT INTO public.equipment(id,type,total_owned_quantity,home_location,created_by)
 VALUES(eq,'VERIFY35 SHARED ROLLBACK 20261022',10,'Isolated verification fixture',owner_id);
 INSERT INTO public.equipment_requirements(id,event_request_id,equipment_type,quantity,recorded_by)
 VALUES(req,e,'VERIFY35 SHARED ROLLBACK 20261022',2,owner_id);
 INSERT INTO public.equipment_reservations(id,equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(res,eq,req,e,1,today+30,today+30,owner_id);
 INSERT INTO public.event_change_requests(id,event_request_id,organiser_id,explanation,proposed_changes,base_event_updated_at)
 SELECT cid,e,owner_id,'Rollback-only rejection verification',payload,updated_at FROM public.event_requests WHERE id=e;
 EXECUTE snapshot_sql INTO before_state USING e,eq,v;
 original:=(SELECT to_jsonb(x) FROM public.event_change_requests x WHERE id=cid);

 -- AC4-H1 (happy): rejection stores its exact audit without applying the plan or changing arrangements/history/jobs.
 started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 saved:=public.reject_event_change_request(e,cid,actor,'  Verification rejection reason  ');
 RESET ROLE;
 ASSERT saved.status='Rejected' AND saved.coordinator_id=actor AND saved.decision_reason='Verification rejection reason'
  AND saved.decided_at BETWEEN started AND clock_timestamp(), 'AC4-H1: rejection audit incorrect';
 ASSERT to_jsonb(saved)-ARRAY['status','coordinator_id','decision_reason','decided_at']
  =original-ARRAY['status','coordinator_id','decision_reason','decided_at'], 'AC4-H1: proposal provenance changed';
 ASSERT (SELECT to_jsonb(x)=to_jsonb(saved) FROM public.event_change_requests x WHERE id=cid), 'AC4-H1: rejection not stored';
 EXECUTE snapshot_sql INTO after_state USING e,eq,v;
 ASSERT after_state-'changes'=before_state-'changes', 'AC4-H1: rejection mutated protected plan/history/work';

 -- AC3-H1 (happy): non-date approval applies only accepted values and creates both domain reviews and pending jobs together.
 cid:=gen_random_uuid();
 INSERT INTO public.event_change_requests(id,event_request_id,organiser_id,explanation,proposed_changes,base_event_updated_at)
 SELECT cid,e,owner_id,'Rollback-only approval verification',payload,updated_at FROM public.event_requests WHERE id=e;
 EXECUTE snapshot_sql INTO before_state USING e,eq,v;
 original:=(SELECT to_jsonb(x) FROM public.event_change_requests x WHERE id=cid);
 before_event:=(SELECT to_jsonb(x) FROM public.event_requests x WHERE id=e);
 started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 saved:=public.approve_non_date_event_change_request(e,cid,actor,'Verified non-date plan');
 RESET ROLE;
 ASSERT saved.status='Approved' AND saved.coordinator_id=actor AND saved.decision_reason='Verified non-date plan'
  AND saved.decided_at BETWEEN started AND clock_timestamp(), 'AC3-H1: approval audit incorrect';
 ASSERT to_jsonb(saved)-ARRAY['status','coordinator_id','decision_reason','decided_at']
  =original-ARRAY['status','coordinator_id','decision_reason','decided_at'], 'AC3-H1: proposal provenance changed';
 ASSERT (SELECT to_jsonb(x)=to_jsonb(saved) FROM public.event_change_requests x WHERE id=cid), 'AC3-H1: approval not stored';
 expected_event:=before_event||payload||jsonb_build_object('updated_at',(SELECT updated_at FROM public.event_requests WHERE id=e));
 ASSERT (SELECT to_jsonb(x)=expected_event AND updated_at>saved.base_event_updated_at FROM public.event_requests x WHERE id=e),
  'AC3-H1: exact plan/version or lifecycle preservation failed';
 ASSERT (SELECT count(*)=2 AND count(DISTINCT trigger_id)=1 AND bool_and(trigger_type='event_change' AND cleared_at IS NULL
  AND strpos(reason,'25')>0 AND strpos(reason,'80')>0) FROM public.arrangement_reviews WHERE event_request_id=e),
  'AC3-H1: complete two-domain review cause/reason missing';
 ASSERT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=e AND arrangement='venue_booking' AND arrangement_id=b
  AND changed_fields @> ARRAY['expected_attendance','venue_requirements'] AND cardinality(changed_fields)=2
  AND strpos(reason,'Seminar room')>0 AND strpos(reason,'Auditorium')>0)
  AND EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=e AND arrangement='equipment_reservation' AND arrangement_id=res
  AND changed_fields @> ARRAY['expected_attendance','equipment_requirements'] AND cardinality(changed_fields)=2
  AND strpos(reason,'Microphone')>0 AND strpos(reason,'Projector')>0), 'AC3-H1: review targets/evidence incorrect';
 ASSERT (SELECT count(*)=2 AND bool_and(j.published_at IS NULL AND j.payload=((to_jsonb(r)-'id')||jsonb_build_object('review_id',r.id)))
  FROM public.arrangement_reviews r JOIN public.arrangement_review_notification_outbox j ON j.review_id=r.id WHERE r.event_request_id=e),
  'AC3-H1: complete immutable pending jobs missing';
 EXECUTE snapshot_sql INTO after_state USING e,eq,v;
 ASSERT after_state-ARRAY['events','changes','reviews','review_jobs']=before_state-ARRAY['events','changes','reviews','review_jobs'],
  'AC3-H1: approval mutated resource/assignment/lifecycle/inbox state';
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_change_requests x WHERE event_request_id=e AND id<>cid)
  =(SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]') FROM jsonb_array_elements(before_state->'changes') x WHERE x->>'id'<>cid::text),
  'AC3-H1: approval changed another saved decision';

 -- AC5-N4 (negative): replay cannot replace audit or add another cause/job.
 before_state:=after_state;
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.approve_non_date_event_change_request(e,cid,actor,NULL); RESET ROLE;
  RAISE EXCEPTION 'AC5-N4: repeated approval accepted' USING ERRCODE='P9901';
 EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
 EXECUTE snapshot_sql INTO after_state USING e,eq,v;
 ASSERT after_state=before_state, 'AC5-N4: replay changed protected fixture state';

 -- AC5-N3/AC6-N1/AC2-N2 (negative): stale, mixed and unassigned decisions refuse without partial changes.
 INSERT INTO public.event_change_requests(id,event_request_id,organiser_id,explanation,proposed_changes,base_event_updated_at)
 SELECT later_cid,e,owner_id,'Rollback-only refusal verification','{"expected_attendance":90}',updated_at-interval '1 second'
 FROM public.event_requests WHERE id=e;
 FOREACH mode IN ARRAY ARRAY['stale','mixed','unassigned'] LOOP
  IF mode='mixed' THEN
   UPDATE public.event_change_requests SET base_event_updated_at=(SELECT updated_at FROM public.event_requests WHERE id=e),
    proposed_changes='{"expected_attendance":90,"proposed_date_times":["2030-01-01T10:00:00+08:00"]}' WHERE id=later_cid;
  END IF;
  EXECUTE snapshot_sql INTO before_state USING e,eq,v;
  BEGIN
   SET LOCAL ROLE service_role;
   PERFORM public.approve_non_date_event_change_request(e,later_cid,CASE WHEN mode='unassigned' THEN wrong_actor ELSE actor END,NULL);
   RESET ROLE;
   RAISE EXCEPTION 'AC6-N1/AC2-N2/AC5-N3: refused approval accepted (%)',mode USING ERRCODE='P9902';
  EXCEPTION WHEN SQLSTATE 'P0004' THEN
   IF mode='unassigned' THEN RAISE; END IF;
  WHEN SQLSTATE 'P0003' THEN
   IF mode<>'unassigned' THEN RAISE; END IF;
  END;
  EXECUTE snapshot_sql INTO after_state USING e,eq,v;
  ASSERT after_state=before_state, 'AC6-N1/AC2-N2/AC5-N3: refused approval changed protected fixture state';
 END LOOP;

 -- AC5-N3 (negative): the rejection boundary also refuses an unassigned actor without writes.
 EXECUTE snapshot_sql INTO before_state USING e,eq,v;
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.reject_event_change_request(e,later_cid,wrong_actor,'Must not be saved'); RESET ROLE;
  RAISE EXCEPTION 'AC5-N3: unassigned rejection accepted' USING ERRCODE='P9903';
 EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
 EXECUTE snapshot_sql INTO after_state USING e,eq,v;
 ASSERT after_state=before_state, 'AC5-N3: refused rejection changed protected fixture state';

 -- AC3-X1 (cross-cutting): browser roles cannot invoke either server-only mutation boundary.
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
  ASSERT NOT has_function_privilege(role_name,'public.reject_event_change_request(uuid,uuid,character varying,text)','EXECUTE')
   AND NOT has_function_privilege(role_name,'public.approve_non_date_event_change_request(uuid,uuid,character varying,text)','EXECUTE'),
   'AC3-X1: browser execute privilege exposed';
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',role_name);
   PERFORM public.reject_event_change_request(e,later_cid,actor,'Must not be saved'); RESET ROLE;
   RAISE EXCEPTION 'AC3-X1: browser rejection executed' USING ERRCODE='P9904';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',role_name);
   PERFORM public.approve_non_date_event_change_request(e,later_cid,actor,NULL); RESET ROLE;
   RAISE EXCEPTION 'AC3-X1: browser approval executed' USING ERRCODE='P9905';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 END LOOP;
 EXECUTE snapshot_sql INTO after_state USING e,eq,v;
 ASSERT after_state=before_state, 'AC3-X1: browser refusal changed protected fixture state';
 RAISE NOTICE 'SCRUM35 shared rollback smoke assertions PASSED; fixture changes remain uncommitted';
END;
$smoke$;
SELECT 'SCRUM35 shared rollback smoke PASSED; next statement rolls back all fixtures' AS result;
ROLLBACK;
