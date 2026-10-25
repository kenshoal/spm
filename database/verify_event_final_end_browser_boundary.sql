-- SCRUM-40 AC1-N8 / AC3-X2: organiser-owned Draft RLS must not grant the authoritative final-end field.
-- Owned disposable database only; Auth claims below are an explicit local double, never a real signed-in proof.
-- All Auth helper replacements/grants and data fixtures roll back together at the final ROLLBACK.
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
 ASSERT to_regprocedure('public.set_event_request_final_end(uuid,character varying,timestamp with time zone)') IS NOT NULL,
  'SETUP: SCRUM40 schema required before browser-field boundary verification';
END $$;
-- TEST INFRASTRUCTURE ONLY: give disposable Auth doubles the request-claim behaviour used by genuine0007 owner RLS.
-- Not JWT verification, not an application auth replacement. Never run on shared Supabase.
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
 ASSERT (SELECT relrowsecurity FROM pg_class WHERE oid='public.event_requests'::regclass),
  'SETUP: actual event RLS must remain enabled';
 ASSERT (SELECT count(*)=4 FROM pg_policy WHERE polrelid='public.event_requests'::regclass
  AND polname IN ('Organisers can create their drafts','Organisers can view their event requests',
   'Organisers can update their drafts','Organisers can delete their drafts')),
  'SETUP: genuine0007 owner policies required; this fixture never substitutes policy business rules';
 ASSERT has_table_privilege('authenticated','public.event_requests','SELECT')
  AND has_table_privilege('authenticated','public.event_requests','INSERT')
  AND has_table_privilege('authenticated','public.event_requests','UPDATE')
  AND has_table_privilege('authenticated','public.event_requests','DELETE'),
  'SETUP: observed existing browser table grants required; no broad table grant is fabricated here';
END $$;
-- Only disposable Auth functions change: policies and account metadata are untouched.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),
  nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid;
$$;
CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT coalesce(nullif(current_setting('request.jwt.claims',true),'')::jsonb,'{}'::jsonb);
$$;
GRANT USAGE ON SCHEMA auth TO authenticated;
GRANT EXECUTE ON FUNCTION auth.uid(),auth.jwt() TO authenticated;

CREATE FUNCTION pg_temp.browser_boundary_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
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
DO $cases$
DECLARE
 owner_id uuid; coordinator uuid:=gen_random_uuid(); draft uuid:=gen_random_uuid(); forbidden uuid:=gen_random_uuid();
 permitted uuid:=gen_random_uuid(); before_state jsonb; after_row jsonb; saved public.event_requests; v_status text;
 deadline timestamptz:='2026-11-25T10:30:00Z';
BEGIN
 SELECT id INTO owner_id FROM auth.users ORDER BY id LIMIT 1;
 ASSERT owner_id IS NOT NULL,'SETUP: disposable Auth FK identity required';
 -- Only local request-claim doubles are configured; neither Auth users nor role metadata rows are modified.
 PERFORM set_config('request.jwt.claim.sub',owner_id::text,true);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('sub',owner_id,'role','authenticated',
  'app_metadata',jsonb_build_object('role','organiser'))::text,true);
 SET LOCAL ROLE authenticated;
 ASSERT auth.uid()=owner_id AND auth.jwt()->'app_metadata'->>'role'='organiser',
  'SETUP: local Auth functions must read request claims so real0007 owner policies are exercised';
 -- AC1-N8 (negative): establish ordinary browser Draft creation/editing first so a table-wide refusal cannot fake a secure end-field boundary.
 INSERT INTO public.event_requests(id,organiser_id,event_name,status)
 VALUES(draft,owner_id,'VERIFY40 organiser ordinary Draft','Draft');
 UPDATE public.event_requests SET description='VERIFY40 ordinary owner edit' WHERE id=draft;
 ASSERT (SELECT description='VERIFY40 ordinary owner edit' AND final_event_end_at IS NULL FROM public.event_requests WHERE id=draft),
  'SETUP: actual authenticated owner Draft INSERT/UPDATE was not permitted';
 RESET ROLE;

 -- AC1-N8 (negative): inherited table INSERT must not permit an organiser to fabricate an authoritative end.
 before_state:=pg_temp.browser_boundary_state();
 BEGIN
  SET LOCAL ROLE authenticated;
  INSERT INTO public.event_requests(id,organiser_id,event_name,status,final_event_end_at)
  VALUES(forbidden,owner_id,'VERIFY40 forbidden browser end INSERT','Draft',deadline);
  RESET ROLE;
  RAISE EXCEPTION 'AC1-N8: authenticated owner inserted an authoritative final end' USING ERRCODE='P9940';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 ASSERT pg_temp.browser_boundary_state()=before_state,'AC1-N8: refused browser end INSERT left protected changes';
 RAISE NOTICE 'PASS AC1-N8 authenticated nonNULL end INSERT denied';

 -- AC1-N8 (negative): inherited table UPDATE must not permit an organiser to set the authoritative end on an owned Draft.
 before_state:=pg_temp.browser_boundary_state();
 BEGIN
  SET LOCAL ROLE authenticated;
  UPDATE public.event_requests SET final_event_end_at=deadline WHERE id=draft;
  RESET ROLE;
  RAISE EXCEPTION 'AC1-N8: authenticated owner updated an authoritative final end' USING ERRCODE='P9940';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 ASSERT pg_temp.browser_boundary_state()=before_state,'AC1-N8: refused browser end UPDATE left protected changes';
 RAISE NOTICE 'PASS AC1-N8 authenticated distinct end UPDATE denied';

 -- AC1-N8 (negative): the narrow field guard preserves ordinary Draft NULL writes and existing owner reads/edits instead of broadening authentication work.
 SET LOCAL ROLE authenticated;
 UPDATE public.event_requests SET event_name='VERIFY40 owner edit still allowed',final_event_end_at=NULL WHERE id=draft;
 ASSERT (SELECT event_name='VERIFY40 owner edit still allowed' AND final_event_end_at IS NULL FROM public.event_requests WHERE id=draft),
  'AC1-N8: end protection broke ordinary owner Draft editing';
 RESET ROLE;
 RAISE NOTICE 'PASS AC1-N8 normal owner Draft reads and edits retained';

 -- AC1-H3 / AC1-P1 (partition): the actual service-only current-coordinator setter continues to work in both approved states.
 FOREACH v_status IN ARRAY ARRAY['Approved','Planning'] LOOP
  permitted:=gen_random_uuid();
  INSERT INTO public.event_requests(id,organiser_id,event_name,status)
  VALUES(permitted,owner_id,'VERIFY40 authorised setter retained',v_status);
  INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
  VALUES(permitted,coordinator::text,'verify40');
  before_state:=pg_temp.browser_boundary_state();
  SET LOCAL ROLE service_role;
  saved:=public.set_event_request_final_end(permitted,coordinator::text,deadline);
  RESET ROLE;
  after_row:=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=permitted);
  ASSERT saved.final_event_end_at=deadline AND to_jsonb(saved)=after_row,
   'AC1-H3: browser field guard broke the authorised service setter';
  ASSERT pg_temp.browser_boundary_state()-'events'=before_state-'events',
   'AC1-H3: authorised end setter changed lifecycle history or related state';
 END LOOP;
 RAISE NOTICE 'PASS AC1-H3 / AC1-P1 service coordinator setter retained';
END $cases$;
ROLLBACK;
