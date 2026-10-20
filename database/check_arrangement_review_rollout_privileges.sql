-- Read-only deployment boundary check; existing AC5-X5/AC3-X3/AC7-X3, no new logical cases.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
DO $$
DECLARE object_name text; role_name text; fn regprocedure; fn_name text;
BEGIN
 -- AC5-X5 (cross-cutting): persisted review and delivery evidence is server-readable without browser or direct server-write access.
 FOREACH object_name IN ARRAY ARRAY['public.arrangement_reviews','public.arrangement_review_notification_outbox'] LOOP
  ASSERT EXISTS(SELECT 1 FROM pg_class WHERE oid=to_regclass(object_name) AND relrowsecurity),
   'AC5-X5: required table missing or RLS disabled: '||object_name;
  ASSERT has_table_privilege('service_role',object_name,'SELECT')
   AND NOT has_table_privilege('service_role',object_name,'INSERT,UPDATE,DELETE,TRUNCATE'),
   'AC5-X5: server table privilege mismatch: '||object_name;
  FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
   ASSERT NOT has_table_privilege(role_name,object_name,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE'),
    'AC5-X5: browser role acquired table access: '||role_name||' '||object_name;
  END LOOP;
 END LOOP;
 -- AC3-X3 (cross-cutting): only server-role callers may execute bounded clear/delivery/shared-read RPCs, with hardened search paths.
 FOREACH fn_name IN ARRAY ARRAY[
  'public.get_outstanding_arrangement_reviews(uuid)',
  'public.clear_arrangement_review(uuid,uuid,text[])',
  'public.begin_arrangement_review_notification_attempt(uuid)',
  'public.record_arrangement_review_notification_accepted(uuid,uuid)',
  'public.complete_arrangement_review_notification(uuid)'] LOOP
  fn:=to_regprocedure(fn_name);
  ASSERT fn IS NOT NULL,'PRECONDITION: required deployed RPC absent: '||fn_name;
  ASSERT has_function_privilege('service_role',fn,'EXECUTE'),'AC3-X3: service RPC execution denied: '||fn_name;
  ASSERT EXISTS(SELECT 1 FROM pg_proc p,unnest(p.proconfig) config WHERE p.oid=fn AND config IN('search_path=','search_path=""')),
   'AC3-X3: RPC search path is not empty: '||fn_name;
  FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
   ASSERT NOT has_function_privilege(role_name,fn,'EXECUTE'),'AC3-X3: browser callable RPC: '||fn_name;
  END LOOP;
 END LOOP;
 -- AC7-X3 (cross-cutting): trigger writers, recipient directory and trusted safety helper are not direct application-role capabilities.
 FOREACH fn_name IN ARRAY ARRAY[
  'private.record_event_arrangement_reviews()',
  'private.record_equipment_unavailability_reviews()',
  'private.enqueue_arrangement_review_notification()',
  'private.arrangement_review_notification_recipients(uuid,text,uuid,text)',
  'private.raise_safety_arrangement_reviews(uuid,uuid,jsonb,text)'] LOOP
  fn:=to_regprocedure(fn_name);
  ASSERT fn IS NOT NULL,'PRECONDITION: required private deployed routine absent: '||fn_name;
  FOREACH role_name IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
   ASSERT NOT has_function_privilege(role_name,fn,'EXECUTE'),'AC7-X3: private routine directly callable: '||role_name||' '||fn_name;
  END LOOP;
 END LOOP;
 RAISE NOTICE 'SCRUM64 read-only rollout privilege/RLS verification PASSED';
END $$;
ROLLBACK;
SELECT 'SCRUM64 read-only rollout privilege/RLS verification PASSED; no state changed' AS verification;
