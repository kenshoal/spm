-- SCRUM-35 rejection-only native contract; real schema, no production substitutes.
-- Prerequisites: genuine event/change/arrangement schema plus rejection-only RPC.
-- HTTP Red is recorded separately; an absent new RPC is only a setup precondition.
BEGIN;
DO $$ BEGIN
    ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
    ASSERT to_regprocedure('public.reject_event_change_request(uuid,uuid,character varying,text)') IS NOT NULL,
      'SETUP: approved rejection-only RPC must be applied before native verification';
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

DO $case$
DECLARE
 owner_id uuid; e1 uuid; e2 uuid; other_event uuid; venue_id uuid; booking_id uuid;
 equipment_id uuid; requirement_id uuid; reservation_id uuid;
 change1 public.event_change_requests; change2 public.event_change_requests; rejected public.event_change_requests;
 before_state jsonb; original_change jsonb; expected_message text; invalid_actor varchar;
 current_actor constant varchar := '35000000-0000-4000-8000-000000000001'; old_actor constant varchar := '35000000-0000-4000-8000-000000000002';
 why constant text := 'The booked arrangements cannot accommodate the requested attendance.';
 current_status text; reason_input text; event_input uuid; change_input uuid;
 reason_length integer; boundary_event uuid; boundary_change public.event_change_requests;
BEGIN
 SELECT id INTO owner_id FROM auth.users ORDER BY created_at LIMIT 1;
 ASSERT owner_id IS NOT NULL, 'SETUP: one disposable Auth identity required';
 INSERT INTO public.event_requests(organiser_id,status,event_name,expected_attendance)
 VALUES(owner_id,'Approved','VERIFY35 rejection Approved',40) RETURNING id INTO e1;
 INSERT INTO public.event_requests(organiser_id,status,event_name,expected_attendance)
 VALUES(owner_id,'Planning','VERIFY35 rejection Planning',40) RETURNING id INTO e2;
 INSERT INTO public.event_requests(organiser_id,status,event_name,expected_attendance)
 VALUES(owner_id,'Approved','VERIFY35 unrelated proposal',40) RETURNING id INTO other_event;
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
 VALUES(e1,current_actor,'verify'),(e2,old_actor,'verify'),(e2,current_actor,'verify'),(other_event,current_actor,'verify');
 INSERT INTO public.venues(name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES('VERIFY35 venue','Test wing',100,'{}','{}','{theatre}','{AM,PM}') RETURNING id INTO venue_id;
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
 VALUES(venue_id,current_actor::uuid,e1,current_date+30,current_date+30,'{AM}','approved',current_actor::uuid,now()) RETURNING id INTO booking_id;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('VERIFY35 microphone',10,'Test store',current_actor::uuid) RETURNING id INTO equipment_id;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(e1,'VERIFY35 microphone',1,current_actor::uuid) RETURNING id INTO requirement_id;
 INSERT INTO public.equipment_reservations(equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(equipment_id,requirement_id,e1,1,current_date+29,current_date+30,current_actor::uuid) RETURNING id INTO reservation_id;
 INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
 VALUES(e1,'venue_booking',booking_id,gen_random_uuid(),'event_change','{expected_attendance}','Existing review must be retained');
 change1:=public.create_event_change_request(e1,owner_id,'Registrations increased.', '{"expected_attendance":80}');
 change2:=public.create_event_change_request(e2,owner_id,'Registrations increased.', '{"expected_attendance":80}');

 -- AC4-H1 (happy): only proposal outcome/audit change; nonempty arrangements/history/reviews/jobs remain identical.
 before_state:=pg_temp.scrum35_state(); original_change:=to_jsonb(change1);
 SET LOCAL ROLE service_role;
 rejected:=public.reject_event_change_request(e1,change1.id,current_actor,'  '||why||'  ');
 RESET ROLE;
 ASSERT rejected.status='Rejected' AND rejected.coordinator_id=current_actor AND rejected.decision_reason=why
   AND rejected.decided_at>=transaction_timestamp() AND rejected.decided_at<=clock_timestamp(), 'AC4-H1: complete current rejection audit missing';
 ASSERT to_jsonb(rejected)-ARRAY['status','coordinator_id','decision_reason','decided_at']
   =original_change-ARRAY['status','coordinator_id','decision_reason','decided_at'], 'AC4-H1: immutable proposal fields changed';
 ASSERT (SELECT to_jsonb(x)=to_jsonb(rejected) FROM public.event_change_requests x WHERE id=change1.id), 'AC4-H1: returned rejection not durably stored';
 ASSERT pg_temp.scrum35_state()-'changes'=before_state-'changes', 'AC4-H1: rejection changed event/arrangements/history/reviews/jobs/inbox';
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_change_requests x WHERE id<>change1.id)
   =(SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]') FROM jsonb_array_elements(before_state->'changes') x WHERE x->>'id'<>change1.id::text), 'AC4-H1: unrelated change rows changed';

 -- AC5-N4 (negative): replay retains the first outcome/actor/time and emits no additional work.
 before_state:=pg_temp.scrum35_state();
 BEGIN
   SET LOCAL ROLE service_role; PERFORM public.reject_event_change_request(e1,change1.id,current_actor,'Replacement must not be stored'); RESET ROLE;
   RAISE EXCEPTION 'AC5-N4: replay accepted' USING ERRCODE='P9904';
 EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state, 'AC5-N4: repeated rejection changed protected state';

 -- AC5-N3 (negative): former and null coordinator identities cannot reject after reassignment.
 FOREACH invalid_actor IN ARRAY ARRAY[old_actor,NULL::varchar] LOOP
   before_state:=pg_temp.scrum35_state();
   BEGIN
     SET LOCAL ROLE service_role; PERFORM public.reject_event_change_request(e2,change2.id,invalid_actor,why); RESET ROLE;
     RAISE EXCEPTION 'AC5-N3: invalid current assignee accepted' USING ERRCODE='P9903';
   EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
   ASSERT pg_temp.scrum35_state()=before_state, 'AC5-N3: refused actor changed state';
 END LOOP;

 -- AC4-N1 (negative): null/blank reasons refuse at the native boundary without partial decisions.
 FOREACH reason_input IN ARRAY ARRAY[NULL::text,'','   ',E'\t\n'] LOOP
   before_state:=pg_temp.scrum35_state();
   BEGIN
     SET LOCAL ROLE service_role; PERFORM public.reject_event_change_request(e2,change2.id,current_actor,reason_input); RESET ROLE;
     RAISE EXCEPTION 'AC4-N1: missing reason accepted' USING ERRCODE='P9901';
   EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
   ASSERT pg_temp.scrum35_state()=before_state, 'AC4-N1: refused reason changed state';
 END LOOP;

 -- AC4-N3 (negative): missing or wrong-event proposal/event identifiers never target a different record.
 FOR event_input,change_input IN VALUES(e2,gen_random_uuid()),(other_event,change2.id),(gen_random_uuid(),change2.id) LOOP
   before_state:=pg_temp.scrum35_state();
   BEGIN
     SET LOCAL ROLE service_role; PERFORM public.reject_event_change_request(event_input,change_input,current_actor,why); RESET ROLE;
     RAISE EXCEPTION 'AC4-N3: missing/wrong-event target accepted' USING ERRCODE='P9902';
   EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
   ASSERT pg_temp.scrum35_state()=before_state, 'AC4-N3: refused target changed state';
 END LOOP;

 -- AC4-N4 (negative): a still-Pending proposal cannot be decided after its event leaves Approved/Planning.
 FOREACH current_status IN ARRAY ARRAY['Submitted','Safety Review','Completed','Cancelled'] LOOP
   UPDATE public.event_requests SET status=current_status WHERE id=e2;
   before_state:=pg_temp.scrum35_state();
   BEGIN
     SET LOCAL ROLE service_role; PERFORM public.reject_event_change_request(e2,change2.id,current_actor,why); RESET ROLE;
     RAISE EXCEPTION 'AC4-N4: ineligible event accepted' USING ERRCODE='P9904';
   EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
   ASSERT pg_temp.scrum35_state()=before_state, 'AC4-N4: refused event state changed protected rows';
 END LOOP;
 UPDATE public.event_requests SET status='Planning',description='An unrelated newer detail' WHERE id=e2;

 -- AC4-X2 (cross-cutting): an unrelated newer event version does not prevent a non-applying rejection.
 ASSERT (SELECT updated_at<>change2.base_event_updated_at FROM public.event_requests WHERE id=e2), 'SETUP: event version must genuinely differ';
 before_state:=pg_temp.scrum35_state();
 SET LOCAL ROLE service_role; rejected:=public.reject_event_change_request(e2,change2.id,current_actor,why); RESET ROLE;
 ASSERT rejected.status='Rejected' AND rejected.coordinator_id=current_actor AND rejected.decision_reason=why, 'AC4-X2: newer version incorrectly blocks rejection';
 ASSERT pg_temp.scrum35_state()-'changes'=before_state-'changes', 'AC4-X2: rejection applied proposal or changed protected state';

 -- AC4-B1, AC4-B2, AC4-B3 (boundary): one/2000-character reasons are retained exactly;2001 refuses without writes.
 FOREACH reason_length IN ARRAY ARRAY[1,2000,2001] LOOP
   INSERT INTO public.event_requests(organiser_id,status,event_name,expected_attendance)
   VALUES(owner_id,'Approved','VERIFY35 reason boundary '||reason_length,40) RETURNING id INTO boundary_event;
   INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
   VALUES(boundary_event,current_actor,'verify');
   boundary_change:=public.create_event_change_request(boundary_event,owner_id,'Boundary proposal.', '{"expected_attendance":80}');
   before_state:=pg_temp.scrum35_state();
   IF reason_length<=2000 THEN
     SET LOCAL ROLE service_role;
     rejected:=public.reject_event_change_request(boundary_event,boundary_change.id,current_actor,repeat('x',reason_length));
     RESET ROLE;
     ASSERT rejected.status='Rejected' AND rejected.decision_reason=repeat('x',reason_length), 'AC4-B1/B2: valid reason boundary was not retained';
     ASSERT pg_temp.scrum35_state()-'changes'=before_state-'changes', 'AC4-B1/B2: boundary rejection changed protected state';
   ELSE
     BEGIN
       SET LOCAL ROLE service_role;
       PERFORM public.reject_event_change_request(boundary_event,boundary_change.id,current_actor,repeat('x',reason_length));
       RESET ROLE;
       RAISE EXCEPTION 'AC4-B3: oversized reason accepted' USING ERRCODE='P9907';
     EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
     ASSERT pg_temp.scrum35_state()=before_state, 'AC4-B3: oversized reason changed protected state';
   END IF;
 END LOOP;

 -- AC4-X3 (cross-cutting): a real audit-write failure rolls the complete rejection operation back.
 change2:=public.create_event_change_request(e2,owner_id,'Another proposal after rejection.', '{"expected_attendance":90}');
 EXECUTE format('CREATE FUNCTION pg_temp.scrum35_reject_fault() RETURNS trigger LANGUAGE plpgsql AS $fault$ BEGIN IF NEW.id=%L::uuid THEN RAISE EXCEPTION ''SCRUM35 injected rejection audit failure'' USING ERRCODE=''23514''; END IF; RETURN NEW; END $fault$',change2.id);
 CREATE TRIGGER scrum35_reject_fault BEFORE UPDATE ON public.event_change_requests FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum35_reject_fault();
 before_state:=pg_temp.scrum35_state();
 BEGIN
   SET LOCAL ROLE service_role; PERFORM public.reject_event_change_request(e2,change2.id,current_actor,why); RESET ROLE;
   RAISE EXCEPTION 'AC4-X3: audit fault not reached' USING ERRCODE='P9905';
 EXCEPTION WHEN check_violation THEN
   GET STACKED DIAGNOSTICS expected_message=MESSAGE_TEXT;
   ASSERT expected_message='SCRUM35 injected rejection audit failure', 'AC4-X3: unrelated failure caught';
 END;
 ASSERT pg_temp.scrum35_state()=before_state, 'AC4-X3: audit failure left partial state';

 -- AC3-X1 (cross-cutting): only the server role can execute this exact narrow mutation; browser calls cannot bypass API identity.
 ASSERT has_function_privilege('service_role','public.reject_event_change_request(uuid,uuid,character varying,text)','EXECUTE');
 ASSERT NOT has_function_privilege('anon','public.reject_event_change_request(uuid,uuid,character varying,text)','EXECUTE');
 ASSERT NOT has_function_privilege('authenticated','public.reject_event_change_request(uuid,uuid,character varying,text)','EXECUTE');
 BEGIN
   SET LOCAL ROLE authenticated; PERFORM public.reject_event_change_request(e2,change2.id,current_actor,why); RESET ROLE;
   RAISE EXCEPTION 'AC3-X1: browser executed rejection' USING ERRCODE='P9906';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 ASSERT pg_temp.scrum35_state()=before_state, 'AC3-X1: browser denial changed state';
 RAISE NOTICE 'SCRUM35 rejection-only native verification PASSED (audit/no-write/stale/role/validation/rollback/privileges; no HTTP notification claim)';
END $case$;
ROLLBACK;
