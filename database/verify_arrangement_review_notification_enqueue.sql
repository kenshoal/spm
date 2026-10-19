-- SCRUM64 AC3: actual new review -> durable pending delivery work in the same transaction.
-- Disposable PG only, existing20 migrations and production-owned0037 outbox scaffold/body.
-- psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_notification_enqueue.sql
-- No recipient resolution, HTTP acceptance, historical-backfill or real-auth claim.
BEGIN;
CREATE TEMP SEQUENCE scrum64_enqueue_attempts;
CREATE FUNCTION pg_temp.scrum64_enqueue_failure() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.event_request_id::text=current_setting('scrum64.notify_fault_event',true) THEN
   IF nextval('pg_temp.scrum64_enqueue_attempts')=2 THEN
     RAISE EXCEPTION 'SCRUM64 injected second notification enqueue failure' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END $$;
-- Missing table is an unimplemented setup precondition, never the behavioural Red.
CREATE TRIGGER scrum64_test_notification_failure BEFORE INSERT ON public.arrangement_review_notification_outbox
 FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum64_enqueue_failure();
CREATE FUNCTION pg_temp.scrum64_notification_state() RETURNS jsonb
LANGUAGE sql STABLE AS $$
SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_requests r),
 'lifecycle',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_status_history r),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r),
 'jobs',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox r),
 'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.venue_booking_requests r),
 'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_reservations r),
 'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_requirements r),
 'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment r),
 'equipment_history',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_status_history r),
 'notifications',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.notifications r),
 'submission_outbox',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_outbox r)
);
$$;
DO $$
DECLARE
 v_actor uuid;
 v_event uuid;
 v_equipment uuid;
 v_venue uuid;
 v_booking uuid;
 v_requirement uuid;
 v_reservation uuid;
 v_trigger_type text;
 v_review public.arrangement_reviews;
 v_expected_payload jsonb;
 v_job jsonb;
 v_before jsonb;
 v_jobs_before jsonb;
 v_submissions_before jsonb;
 v_today date:=(transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
 v_message text;
 v_writer record;
 v_writers integer:=0;
 v_role text;
BEGIN
 SELECT id INTO v_actor FROM auth.users ORDER BY id LIMIT 1;
 ASSERT v_actor IS NOT NULL, 'fixture: disposable auth identity required';
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(v_actor,'VERIFY SCRUM64 durable review notification','Planning',25) RETURNING id INTO v_event;
 INSERT INTO public.venues(name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES('VERIFY SCRUM64 notification venue','Test wing',100,'{}','{}',
  ARRAY['theatre']::public.room_layout[],ARRAY['AM']::public.booking_slot[]) RETURNING id INTO v_venue;
 INSERT INTO public.venue_booking_requests
 (venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
 VALUES(v_venue,v_actor,v_event,v_today-1,v_today,ARRAY['AM']::public.booking_slot[],
  'approved',v_actor,transaction_timestamp()) RETURNING id INTO v_booking;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('VERIFY SCRUM64 notification microphone',10,'Test store',v_actor) RETURNING id INTO v_equipment;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(v_event,'VERIFY SCRUM64 notification microphone',10,v_actor) RETURNING id INTO v_requirement;
 INSERT INTO public.equipment_reservations
 (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(v_equipment,v_requirement,v_event,1,v_today-1,v_today,v_actor) RETURNING id INTO v_reservation;
 SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') INTO v_submissions_before FROM public.event_request_outbox r;

 -- AC3-P1 (partition): a new event-change flag atomically persists its complete pending notification facts.
 -- AC3-P2 (partition): equipment unavailability uses the same durable delivery boundary without a fabricated change request.
 -- AC3-P3 (partition): an explicit safety cause preserves its actual decision UUID and complete reason in durable work.
 FOREACH v_trigger_type IN ARRAY ARRAY['event_change','equipment_unavailable','safety_recheck'] LOOP
   INSERT INTO public.arrangement_reviews
    (event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
   VALUES(v_event,CASE WHEN v_trigger_type='equipment_unavailable' THEN 'equipment_reservation' ELSE 'venue_booking' END,
    CASE WHEN v_trigger_type='equipment_unavailable' THEN v_reservation ELSE v_booking END,
    gen_random_uuid(),v_trigger_type,
    CASE WHEN v_trigger_type='event_change' THEN ARRAY['expected_attendance'] ELSE ARRAY[]::text[] END,
    'Specific full review reason: '||v_trigger_type) RETURNING * INTO v_review;
   ASSERT (SELECT count(*)=1 FROM public.arrangement_review_notification_outbox WHERE review_id=v_review.id),
    'AC3-P1/P2/P3: actual new flag must persist one pending notification job';
   v_expected_payload:=(to_jsonb(v_review)-'id')||jsonb_build_object('review_id',v_review.id);
   SELECT to_jsonb(j) INTO v_job FROM public.arrangement_review_notification_outbox j WHERE review_id=v_review.id;
   ASSERT v_job->>'event_request_id'=v_event::text AND v_job->'payload'=v_expected_payload
    AND NOT(v_job->'payload' ? 'change_request_id') AND v_job->>'published_at' IS NULL
    AND (v_job->>'occurred_at')::timestamptz>=transaction_timestamp()
    AND (v_job->>'occurred_at')::timestamptz<=clock_timestamp(),
    'AC3-P1/P2/P3: job lost immutable review evidence, invented a change request or prematurely completed';
 END LOOP;
 ASSERT (SELECT count(*)=3 FROM public.arrangement_review_notification_outbox WHERE event_request_id=v_event),
  'AC3-P1/P2/P3: wrong durable job count across causes';
 ASSERT (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_outbox r)=v_submissions_before,
  'AC3-P1/P2/P3: arrangement delivery changed the submission outbox';

 -- AC3-N1 (negative): exact cause replay, clearing and unrelated edits cannot enqueue twice or rewrite the raised snapshot.
 SELECT jsonb_agg(to_jsonb(r) ORDER BY review_id) INTO v_jobs_before
 FROM public.arrangement_review_notification_outbox r WHERE event_request_id=v_event;
 INSERT INTO public.arrangement_reviews
  (event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
 VALUES(v_review.event_request_id,v_review.arrangement,v_review.arrangement_id,v_review.trigger_id,
  v_review.trigger_type,v_review.changed_fields,v_review.reason) ON CONFLICT DO NOTHING;
 SET LOCAL ROLE service_role;
 PERFORM public.clear_arrangement_review(v_review.id,v_actor,ARRAY['venue_booking']);
 UPDATE public.event_requests SET description='Unrelated notification fixture edit' WHERE id=v_event;
 RESET ROLE;
 ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY review_id) FROM public.arrangement_review_notification_outbox r
  WHERE event_request_id=v_event)=v_jobs_before, 'AC3-N1: replay/clear/unrelated edit changed queued original facts';

 -- AC3-X1 (cross-cutting): second real enqueue failure aborts accepted event change, both reviews and both jobs atomically.
 v_before:=pg_temp.scrum64_notification_state();
 PERFORM set_config('scrum64.notify_fault_event',v_event::text,true);
 BEGIN
  SET LOCAL ROLE service_role;
  UPDATE public.event_requests SET expected_attendance=40 WHERE id=v_event;
  RESET ROLE;
  RAISE EXCEPTION 'AC3-X1: expected second notification enqueue failure';
 EXCEPTION WHEN check_violation THEN
  GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT;
  ASSERT v_message='SCRUM64 injected second notification enqueue failure', 'AC3-X1: unrelated failure caught';
 END;
 ASSERT currval('pg_temp.scrum64_enqueue_attempts')=2, 'AC3-X1: second actual enqueue not attempted';
 ASSERT pg_temp.scrum64_notification_state()=v_before, 'AC3-X1: enqueue failure left event/review/job/resource changes';

 -- AC3-X1 (cross-cutting): audit enqueue stays private and grants only server reads in this first slice.
 ASSERT (SELECT relrowsecurity FROM pg_class WHERE oid='public.arrangement_review_notification_outbox'::regclass),
  'AC3-X1: outbox RLS missing';
 ASSERT has_table_privilege('service_role','public.arrangement_review_notification_outbox','SELECT')
  AND NOT has_table_privilege('service_role','public.arrangement_review_notification_outbox','INSERT')
  AND NOT has_table_privilege('service_role','public.arrangement_review_notification_outbox','UPDATE'),
  'AC3-X1: first-stage service grants broadened notification mutation';
 FOR v_writer IN SELECT p.oid,p.prosecdef,p.proconfig,n.nspname
  FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE t.tgrelid='public.arrangement_reviews'::regclass AND NOT t.tgisinternal
   AND (t.tgtype::integer & 4)=4 AND (t.tgtype::integer & 2)=0
 LOOP
  v_writers:=v_writers+1;
  ASSERT v_writer.prosecdef AND v_writer.nspname='private'
   AND EXISTS(SELECT 1 FROM unnest(v_writer.proconfig) c WHERE c IN('search_path=','search_path=""')),
   'AC3-X1: enqueue writer is not private definer with empty search_path';
  FOREACH v_role IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
   ASSERT NOT has_function_privilege(v_role,v_writer.oid,'EXECUTE'), 'AC3-X1: caller can directly invoke enqueue writer';
  END LOOP;
 END LOOP;
 ASSERT v_writers>0, 'AC3-X1: no private enqueue writer found';
 FOREACH v_role IN ARRAY ARRAY['anon','authenticated'] LOOP
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',v_role);
   PERFORM 1 FROM public.arrangement_review_notification_outbox;
   RAISE EXCEPTION 'AC3-X1: browser read private delivery jobs';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
 END LOOP;
 ASSERT pg_temp.scrum64_notification_state()=v_before, 'AC3-X1: denied access changed protected state';
 RAISE NOTICE 'SCRUM64 notification enqueue verification PASSED (five IDs; not recipient/delivery proof)';
END $$;
ROLLBACK;
