-- AC5-X2 (cross-cutting): shared outstanding evidence is protected, ordered and refreshed after exact clears.
-- This returns facts/reasons, not a readiness verdict or SCRUM58 handover.
-- Disposable PostgreSQL only after upstream0029, review0030-0033 and shared-read DDL.
-- Run psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_shared_reads.sql.
BEGIN;
CREATE FUNCTION pg_temp.scrum64_shared_read_snapshot() RETURNS jsonb
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
 v_oid oid:=to_regprocedure('public.get_outstanding_arrangement_reviews(uuid)');
 v_before jsonb;
 v_expected jsonb;
 v_actual jsonb;
 v_role text;
 v_index integer;
 v_ids uuid[]:=ARRAY['64000000-0000-4000-8000-000000000001',
                     '64000000-0000-4000-8000-000000000003',
                     '64000000-0000-4000-8000-000000000002']::uuid[];
BEGIN
 ASSERT v_oid IS NOT NULL, 'AC5-X2 setup: shared-read function must be implemented before native verification';
 ASSERT (SELECT NOT prosecdef AND provolatile='s' AND proretset
   AND prorettype='public.arrangement_reviews'::regtype
   AND EXISTS(SELECT 1 FROM unnest(proconfig) c WHERE c IN('search_path=','search_path=""'))
   FROM pg_proc WHERE oid=v_oid), 'AC5-X2: shared helper must be STABLE INVOKER with empty search_path and full row-set contract';
 ASSERT has_function_privilege('service_role',v_oid,'EXECUTE')
   AND NOT has_function_privilege('anon',v_oid,'EXECUTE')
   AND NOT has_function_privilege('authenticated',v_oid,'EXECUTE'),
   'AC5-X2: helper EXECUTE boundary is not server-only';
 ASSERT NOT has_table_privilege('service_role','public.arrangement_reviews','UPDATE')
   AND NOT has_table_privilege('service_role','public.arrangement_reviews','INSERT'),
   'AC5-X2: shared read broadened review mutation grants';
 SELECT id INTO v_actor FROM auth.users ORDER BY id LIMIT 1;
 ASSERT v_actor IS NOT NULL, 'fixture: disposable auth identity required';
 INSERT INTO public.event_requests(organiser_id,event_name,status)
 VALUES(v_actor,'VERIFY SCRUM64 shared facts Safety Review','Safety Review') RETURNING id INTO v_event;
 INSERT INTO public.event_requests(organiser_id,event_name,status)
 VALUES(v_actor,'VERIFY SCRUM64 other shared facts','Planning') RETURNING id INTO v_other;
 INSERT INTO public.arrangement_reviews
 (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at,cleared_at,cleared_by)
 VALUES
 (v_ids[1],v_event,'venue_booking',gen_random_uuid(),gen_random_uuid(),'event_change',
  ARRAY['expected_attendance'],'Attendance 25 -> 40; retain full venue reason','2026-10-14 23:30:00-02',NULL,NULL),
 (v_ids[3],v_event,'equipment_reservation',gen_random_uuid(),gen_random_uuid(),'equipment_unavailable',
  ARRAY['operational_status'],'AVAILABLE -> DAMAGED; retain full equipment reason','2026-10-15 01:00:00Z',NULL,NULL),
 (v_ids[2],v_event,'equipment_reservation',gen_random_uuid(),gen_random_uuid(),'safety_recheck',
  ARRAY[]::text[],'Explicit safety instruction; retain full target reason','2026-10-15 09:00:00+08',NULL,NULL),
 ('64000000-0000-4000-8000-000000000004',v_event,'venue_booking',gen_random_uuid(),gen_random_uuid(),'safety_recheck',
  ARRAY[]::text[],'Already cleared, not outstanding','2026-10-15 03:00:00Z',transaction_timestamp(),v_actor),
 ('64000000-0000-4000-8000-000000000009',v_other,'venue_booking',gen_random_uuid(),gen_random_uuid(),'event_change',
  ARRAY['expected_attendance'],'Other event private reason','2026-10-15 05:00:00Z',NULL,NULL);
 v_before:=pg_temp.scrum64_shared_read_snapshot();
 SELECT jsonb_agg(to_jsonb(r) ORDER BY array_position(v_ids,id)) INTO v_expected
 FROM public.arrangement_reviews r WHERE id=ANY(v_ids);
 SET LOCAL ROLE service_role;
 SELECT jsonb_agg(to_jsonb(r)) INTO v_actual FROM public.get_outstanding_arrangement_reviews(v_event) r;
 RESET ROLE;
 ASSERT v_actual=v_expected, 'AC5-X2: full outstanding evidence, event scope, absolute time or UUID tie order differs';
 ASSERT pg_temp.scrum64_shared_read_snapshot()=v_before, 'AC5-X2: read mutated protected state';

 -- AC5-X2 (cross-cutting): actual browser calls fail42501, never return another event or mutate facts.
 FOREACH v_role IN ARRAY ARRAY['anon','authenticated'] LOOP
   BEGIN
     EXECUTE format('SET LOCAL ROLE %I',v_role);
     PERFORM public.get_outstanding_arrangement_reviews(v_event);
     RAISE EXCEPTION 'AC5-X2: browser called shared outstanding helper';
   EXCEPTION WHEN insufficient_privilege THEN NULL;
   END;
 END LOOP;
 ASSERT pg_temp.scrum64_shared_read_snapshot()=v_before, 'AC5-X2: denied browser calls changed state';

 -- AC5-X2 (cross-cutting): the SAME helper exposes remaining evidence2->1->0 after legitimate exact-ID clearing.
 FOR v_index IN 1..3 LOOP
   SET LOCAL ROLE service_role;
   PERFORM public.clear_arrangement_review(v_ids[v_index],v_actor,
     CASE WHEN v_index=1 THEN ARRAY['venue_booking'] ELSE ARRAY['equipment_reservation'] END);
   RESET ROLE;
   v_before:=pg_temp.scrum64_shared_read_snapshot();
   SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY array_position(v_ids,id)),'[]') INTO v_expected
   FROM public.arrangement_reviews r WHERE id=ANY(v_ids) AND array_position(v_ids,id)>v_index;
   SET LOCAL ROLE service_role;
   SELECT coalesce(jsonb_agg(to_jsonb(r)),'[]') INTO v_actual
   FROM public.get_outstanding_arrangement_reviews(v_event) r;
   RESET ROLE;
   ASSERT jsonb_array_length(v_actual)=3-v_index AND v_actual=v_expected,
     'AC5-X2: helper omitted an outstanding reason or retained cleared work';
   ASSERT pg_temp.scrum64_shared_read_snapshot()=v_before, 'AC5-X2: refreshed read mutated state';
 END LOOP;
 ASSERT (SELECT status='Safety Review' FROM public.event_requests WHERE id=v_event),
   'AC5-X2: shared facts/clearing performed a readiness lifecycle decision';
 ASSERT (SELECT count(*)=1 FROM public.event_request_status_history WHERE event_request_id=v_event),
   'AC5-X2: shared facts/clearing appended lifecycle history';
 RAISE NOTICE 'AC5-X2 shared outstanding evidence verification PASSED';
END $$;
ROLLBACK;
