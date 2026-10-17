-- SCRUM64 AC3: native current-recipient and durable partial-acceptance contract.
-- DISPOSABLE DATABASE ONLY: temporarily renames the local auth.users double.
-- Requires production-owned0038 callable seam; absence is setup, never behavioural Red.
-- psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_notification_delivery.sql
BEGIN;
CREATE FUNCTION pg_temp.scrum64_delivery_protected() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_requests x),
 'history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_status_history x),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.arrangement_reviews x),
 'source_work',(SELECT coalesce(jsonb_agg(jsonb_build_object('review_id',review_id,'event_request_id',event_request_id,'payload',payload,'occurred_at',occurred_at) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox),
 'notifications',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.notifications x),
 'submission_work',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_outbox x));
$$;
DO $$
DECLARE
 owner_id uuid; c1 uuid:=gen_random_uuid(); c2 uuid:=gen_random_uuid(); staff uuid:=gen_random_uuid();
 meta_list uuid:=gen_random_uuid(); meta_primary uuid:=gen_random_uuid(); scalar_roles uuid:=gen_random_uuid();
 suppressed uuid:=gen_random_uuid(); dangling uuid:=gen_random_uuid(); e1 uuid; e2 uuid;
 approved uuid:=gen_random_uuid(); other_change uuid:=gen_random_uuid(); pending_change uuid:=gen_random_uuid();
 main uuid:=gen_random_uuid(); cross_job uuid:=gen_random_uuid(); waiting uuid:=gen_random_uuid();
 equipment_job uuid:=gen_random_uuid(); no_coord uuid:=gen_random_uuid(); r uuid; recipient uuid;
 s jsonb; before_state jsonb; completed_row jsonb; expected_payload jsonb; ids uuid[]; first_job uuid;
 prior_time text:='2026-10-14T01:02:03+00:00'; started timestamptz; role_name text; fn regprocedure;
BEGIN
 ASSERT to_regprocedure('public.begin_arrangement_review_notification_attempt(uuid)') IS NOT NULL,
  'setup: production attempt callable required';
 ASSERT to_regprocedure('public.record_arrangement_review_notification_accepted(uuid,uuid)') IS NOT NULL,
  'setup: production acceptance callable required';
 ASSERT to_regprocedure('public.complete_arrangement_review_notification(uuid)') IS NOT NULL,
  'setup: production completion callable required';
 SELECT id INTO owner_id FROM auth.users ORDER BY id LIMIT 1;
 ASSERT owner_id IS NOT NULL,'setup: disposable auth owner required';
 INSERT INTO auth.users(id,raw_app_meta_data) VALUES
 (c1,'{"roles":["technical_support"]}'),(c2,'{"role":"event_coordinator"}'),
 (staff,'{"roles":["technical_support"]}'),(meta_list,'{"roles":[123,null,"venue_staff"]}'),
 (meta_primary,'{"roles":[123,null],"role":"venue_staff"}'),
 (scalar_roles,'{"roles":"venue_staff","role":"technical_support"}'),
 (suppressed,'{"roles":["venue_staff"]}');
 INSERT INTO public.staff_roles(user_id,role) VALUES
 (c1,'event_coordinator'),(c1,'venue_staff'),(staff,'venue_staff'),(suppressed,'attendee'),(dangling,'venue_staff');
 INSERT INTO public.event_requests(organiser_id,event_name,status) VALUES
 (owner_id,'VERIFY SCRUM64 recipient resolution','Planning') RETURNING id INTO e1;
 INSERT INTO public.event_requests(organiser_id,event_name,status) VALUES
 (owner_id,'VERIFY SCRUM64 missing coordinator','Planning') RETURNING id INTO e2;
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
 VALUES(e1,c1::text,owner_id::text);
 INSERT INTO public.event_change_requests
 (id,event_request_id,organiser_id,status,explanation,proposed_changes,base_event_updated_at) VALUES
 (approved,e1,owner_id,'Approved','Accepted actual cause','{"expected_attendance":40}',transaction_timestamp()),
 (other_change,e2,owner_id,'Approved','Other event cause','{"expected_attendance":40}',transaction_timestamp()),
 (pending_change,e1,owner_id,'Pending','Not accepted','{"expected_attendance":40}',transaction_timestamp());
 INSERT INTO public.arrangement_reviews(id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason) VALUES
 (main,e1,'venue_booking',gen_random_uuid(),approved,'event_change',ARRAY['expected_attendance'],'Exact original reason 25 to 40'),
 (cross_job,e1,'venue_booking',gen_random_uuid(),other_change,'event_change','{}','Other-event reference stays generic'),
 (waiting,e1,'venue_booking',gen_random_uuid(),pending_change,'event_change','{}','Pending reference stays generic'),
 (equipment_job,e1,'equipment_reservation',gen_random_uuid(),approved,'equipment_unavailable','{}','Actual equipment cause'),
 (no_coord,e2,'venue_booking',gen_random_uuid(),gen_random_uuid(),'safety_recheck','{}','No coordinator yet');
 UPDATE public.arrangement_review_notification_outbox SET occurred_at=transaction_timestamp()-interval '5 hours' WHERE review_id=main;
 UPDATE public.arrangement_review_notification_outbox SET occurred_at=transaction_timestamp()-interval '4 hours' WHERE review_id=cross_job;
 before_state:=pg_temp.scrum64_delivery_protected();
 -- AC3-H1 (happy): authoritative current groups, full evidence and genuine accepted cause are resolved together.
 SET LOCAL ROLE service_role;
 s:=public.begin_arrangement_review_notification_attempt(main);
 RESET ROLE;
 ASSERT s IS NOT NULL AND (s->>'recipients_available')::boolean AND s->>'coordinator_id'=c1::text,
  'AC3-H1: current assigned coordinator not resolved';
 SELECT array_agg(value::uuid ORDER BY value::uuid) INTO ids FROM jsonb_array_elements_text(s->'domain_recipient_ids');
 ASSERT ids=(SELECT array_agg(x ORDER BY x) FROM unnest(ARRAY[c1,staff,meta_list,meta_primary]) x),
  'AC3-H1: effective role precedence, metadata parsing or existing-account membership incorrect';
 SELECT j.payload INTO expected_payload FROM public.arrangement_review_notification_outbox j WHERE review_id=main;
 ASSERT s->'payload'=expected_payload AND s->>'review_id'=main::text AND s->'accepted_recipients'='{}'::jsonb
  AND s->>'change_request_id'=approved::text,'AC3-H1: evidence or genuine same-event Approved cause lost';
 -- AC3-X3 (cross-cutting): attempting unresolved oldest work rotates it behind never-attempted work.
 SELECT review_id INTO first_job FROM public.arrangement_review_notification_outbox
 WHERE published_at IS NULL ORDER BY last_attempted_at ASC NULLS FIRST,occurred_at,review_id LIMIT 1;
 ASSERT first_job=cross_job AND (SELECT last_attempted_at IS NOT NULL AND published_at IS NULL
 FROM public.arrangement_review_notification_outbox WHERE review_id=main),'AC3-X3: attempt stamp cannot support fair retry';
 FOREACH r IN ARRAY ARRAY[cross_job,waiting,equipment_job] LOOP
  SET LOCAL ROLE service_role; s:=public.begin_arrangement_review_notification_attempt(r); RESET ROLE;
  ASSERT s->>'change_request_id' IS NULL,'AC3-H1: unrelated, pending or equipment cause invented a change request';
 END LOOP;
 -- AC3-P2 (partition): equipment work resolves technical capability, never a hardcoded venue queue or suppressed metadata.
 SELECT array_agg(value::uuid ORDER BY value::uuid) INTO ids FROM jsonb_array_elements_text(s->'domain_recipient_ids');
 ASSERT ids=ARRAY[scalar_roles] AND s->>'coordinator_id'=c1::text,
  'AC3-P2: equipment delivery resolved the wrong domain or ignored role precedence';
 -- AC3-N1 (negative): partial acceptance survives retry and reassignment without resetting first accepted times.
 UPDATE public.arrangement_review_notification_outbox SET accepted_recipients=jsonb_build_object(c1::text,prior_time) WHERE review_id=main;
 FOREACH recipient IN ARRAY ARRAY[c1,staff,meta_list,meta_primary] LOOP
  SET LOCAL ROLE service_role; PERFORM public.record_arrangement_review_notification_accepted(main,recipient); RESET ROLE;
 END LOOP;
 ASSERT (SELECT accepted_recipients->>c1::text=prior_time AND (SELECT count(*)=4 FROM jsonb_object_keys(accepted_recipients))
 FROM public.arrangement_review_notification_outbox WHERE review_id=main),'AC3-N1: acceptance overwritten or lost';
 DELETE FROM public.staff_roles WHERE user_id=c1;
 INSERT INTO public.staff_roles(user_id,role) VALUES(c1,'attendee');
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by,assigned_at)
 VALUES(e1,c2::text,owner_id::text,clock_timestamp()+interval '1 second');
 SET LOCAL ROLE service_role;
 ASSERT NOT public.complete_arrangement_review_notification(main),'AC3-N1: published using former assignment';
 s:=public.begin_arrangement_review_notification_attempt(main);
 RESET ROLE;
 ASSERT s->>'coordinator_id'=c2::text AND NOT(s->'domain_recipient_ids' @> to_jsonb(ARRAY[c1]))
 AND s->'accepted_recipients'->>c1::text=prior_time,'AC3-N1: current groups/old acceptance incorrect';
 started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 PERFORM public.record_arrangement_review_notification_accepted(main,c2);
 ASSERT public.complete_arrangement_review_notification(main),'AC3-N1: complete current union failed';
 RESET ROLE;
 ASSERT (SELECT published_at>=started AND published_at<=clock_timestamp() FROM public.arrangement_review_notification_outbox WHERE review_id=main),
 'AC3-N1: acceptance completion timestamp missing';
 SELECT to_jsonb(j) INTO completed_row FROM public.arrangement_review_notification_outbox j WHERE review_id=main;
 SET LOCAL ROLE service_role;
 PERFORM public.complete_arrangement_review_notification(main);
 ASSERT public.begin_arrangement_review_notification_attempt(main) IS NULL,'AC3-N1: published work attempted again';
 RESET ROLE;
 ASSERT (SELECT to_jsonb(j) FROM public.arrangement_review_notification_outbox j WHERE review_id=main)=completed_row,
 'AC3-N1: repeated completion changed first published/accepted evidence';
 -- AC3-B1 (boundary): a missing or revoked coordinator leaves durable work unresolved despite domain acceptance.
 SET LOCAL ROLE service_role; s:=public.begin_arrangement_review_notification_attempt(no_coord); RESET ROLE;
 ASSERT s->>'coordinator_id' IS NULL AND jsonb_array_length(s->'domain_recipient_ids')>0,
 'AC3-B1: missing coordinator fixture not represented';
 FOR recipient IN SELECT value::uuid FROM jsonb_array_elements_text(s->'domain_recipient_ids') LOOP
 SET LOCAL ROLE service_role; PERFORM public.record_arrangement_review_notification_accepted(no_coord,recipient); RESET ROLE;
 END LOOP;
 SET LOCAL ROLE service_role; ASSERT NOT public.complete_arrangement_review_notification(no_coord),'AC3-B1: missing coordinator falsely complete'; RESET ROLE;
 INSERT INTO public.staff_roles(user_id,role) VALUES(c2,'attendee');
 SET LOCAL ROLE service_role; s:=public.begin_arrangement_review_notification_attempt(cross_job); RESET ROLE;
 ASSERT s->>'coordinator_id' IS NULL,'AC3-B1: revoked coordinator retained capability';
 DELETE FROM public.staff_roles WHERE user_id=c2;
 -- AC3-B2 (boundary): a valid coordinator alone cannot satisfy an empty current domain queue.
 UPDATE public.staff_roles SET role='attendee' WHERE user_id=staff AND role='venue_staff';
 UPDATE auth.users SET raw_app_meta_data='{"role":"attendee"}' WHERE id IN(meta_list,meta_primary);
 SET LOCAL ROLE service_role; s:=public.begin_arrangement_review_notification_attempt(cross_job);
 PERFORM public.record_arrangement_review_notification_accepted(cross_job,c2);
 ASSERT NOT public.complete_arrangement_review_notification(cross_job),'AC3-B2: empty staff queue falsely complete'; RESET ROLE;
 ASSERT s->>'coordinator_id'=c2::text AND s->'domain_recipient_ids'='[]'::jsonb,'AC3-B2: empty-domain boundary not represented';
 ASSERT pg_temp.scrum64_delivery_protected()=before_state,'AC3: recipient work changed source review/event/history/inbox';
 PERFORM set_config('scrum64.delivery_fault_review',cross_job::text,true);
 PERFORM set_config('scrum64.delivery_protected',before_state::text,true);
 -- AC3-X3 (cross-cutting): only hardened service RPCs can mutate acceptance/publication, never direct caller writes.
 FOREACH fn IN ARRAY ARRAY['public.begin_arrangement_review_notification_attempt(uuid)'::regprocedure,
 'public.record_arrangement_review_notification_accepted(uuid,uuid)'::regprocedure,
 'public.complete_arrangement_review_notification(uuid)'::regprocedure] LOOP
 ASSERT (SELECT prosecdef AND EXISTS(SELECT 1 FROM unnest(proconfig) c WHERE c IN('search_path=','search_path=""')) FROM pg_proc WHERE oid=fn),
 'AC3-X3: notification RPC privilege/search_path unsafe';
 ASSERT has_function_privilege('service_role',fn,'EXECUTE'),'AC3-X3: service cannot call bounded RPC';
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
 ASSERT NOT has_function_privilege(role_name,fn,'EXECUTE'),'AC3-X3: browser callable notification mutator';
 END LOOP;
 END LOOP;
 ASSERT NOT has_table_privilege('service_role','public.arrangement_review_notification_outbox','UPDATE')
 AND NOT has_table_privilege('service_role','public.arrangement_reviews','UPDATE'),'AC3-X3: broad server table update granted';
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
 BEGIN
 EXECUTE format('SET LOCAL ROLE %I',role_name);
 PERFORM public.begin_arrangement_review_notification_attempt(main);
 RAISE EXCEPTION 'AC3-X3: browser executed notification attempt';
 EXCEPTION WHEN insufficient_privilege THEN NULL;
 END;
 END LOOP;
END $$;
-- AC3-N4 (negative): a real disposable directory lookup failure retains the attempt stamp and safe unresolved work.
ALTER TABLE auth.users RENAME TO scrum64_unavailable_auth_users;
DISCARD PLANS;
DO $$
DECLARE r uuid:=current_setting('scrum64.delivery_fault_review')::uuid; before_row jsonb; after_row jsonb; s jsonb; started timestamptz;
BEGIN
 SELECT to_jsonb(j) INTO before_row FROM public.arrangement_review_notification_outbox j WHERE review_id=r;
 started:=clock_timestamp();
 SET LOCAL ROLE service_role; s:=public.begin_arrangement_review_notification_attempt(r); RESET ROLE;
 SELECT to_jsonb(j) INTO after_row FROM public.arrangement_review_notification_outbox j WHERE review_id=r;
 ASSERT s->'recipients_available'='false'::jsonb,'AC3-N4: directory failure disguised as resolved empty groups';
 ASSERT (after_row->>'last_attempted_at')::timestamptz>=started AND (after_row-'last_attempted_at')=(before_row-'last_attempted_at'),
 'AC3-N4: failure lost attempt stamp or changed other work fields';
END $$;
ALTER TABLE auth.scrum64_unavailable_auth_users RENAME TO users;
DISCARD PLANS;
DO $$ BEGIN
 ASSERT pg_temp.scrum64_delivery_protected()=current_setting('scrum64.delivery_protected')::jsonb,
 'AC3-N4: lookup failure mutated protected source facts';
 RAISE NOTICE 'SCRUM64 native notification delivery PASSED (AC3-H1/N1/B1/B2/N4/X3; no HTTP or real-auth claim)';
END $$;
ROLLBACK;
