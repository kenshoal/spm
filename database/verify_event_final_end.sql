-- SCRUM-40 authoritative end recording, no-op version and reschedule invalidation.
-- Disposable-only full snapshots; no shared fixture writes.
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
 ASSERT to_regprocedure('public.set_event_request_final_end(uuid,character varying,timestamp with time zone)') IS NOT NULL,
  'SETUP: production-owned callable setter scaffold required, not feature Red';
END $$;
CREATE FUNCTION pg_temp.end_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
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
 owner_id uuid; e uuid; b uuid; saved public.event_requests;
 actor varchar:='40000000-0000-4000-8000-000000000001';
 former varchar:='40000000-0000-4000-8000-000000000002';
 invalid_actor varchar; v_status text; field text;
 before_state jsonb; before_event jsonb; expected jsonb; started timestamptz;
 end_at timestamptz:='2026-11-25T18:30:00+08:00';
BEGIN
 SELECT id INTO owner_id FROM auth.users ORDER BY id LIMIT 1;
 ASSERT owner_id IS NOT NULL,'SETUP: disposable Auth fixture required';
 -- AC1-H3, AC1-P1 (partition): both approved editable states persist only end/version with current-assignee authority.
 FOREACH v_status IN ARRAY ARRAY['Approved','Planning'] LOOP
  INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance,proposed_date_times)
  VALUES(owner_id,'VERIFY40 final end',v_status,25,ARRAY['2026-11-25T02:00:00Z'::timestamptz]) RETURNING id INTO e;
  INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
  VALUES(e,former,'verify40'),(e,actor,'verify40');
  before_state:=pg_temp.end_state();
  before_event:=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=e);
  SET LOCAL ROLE service_role; saved:=public.set_event_request_final_end(e,actor,end_at); RESET ROLE;
  ASSERT saved.final_event_end_at=end_at AND (SELECT final_event_end_at=end_at FROM public.event_requests WHERE id=e),
   'AC1-H3: authoritative final end was not persisted';
  expected:=before_event||jsonb_build_object('final_event_end_at',end_at,'updated_at',saved.updated_at);
  ASSERT to_jsonb(saved)=expected AND saved.updated_at>(before_event->>'updated_at')::timestamptz
   AND (SELECT to_jsonb(r)=expected FROM public.event_requests r WHERE id=e), 'AC1-H3: setter changed other event fields or returned an unsaved row';
  ASSERT pg_temp.end_state()-'events'=before_state-'events', 'AC1-H3: recording an end changed lifecycle history or related state';

  -- AC1-B5 (boundary): a timezone-equivalent same instant is a real no-op, including the event version.
  before_state:=pg_temp.end_state();
  SET LOCAL ROLE service_role; saved:=public.set_event_request_final_end(e,actor,'2026-11-25T10:30:00Z'); RESET ROLE;
  ASSERT pg_temp.end_state()=before_state AND to_jsonb(saved)=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=e),
   'AC1-B5: same instant rewrote version or related state';

  -- AC1-N3 (negative): latest assignment is rechecked natively, including NULL actor, with zero writes.
  FOREACH invalid_actor IN ARRAY ARRAY[former,NULL::varchar] LOOP
   before_state:=pg_temp.end_state();
   BEGIN
    SET LOCAL ROLE service_role; PERFORM public.set_event_request_final_end(e,invalid_actor,end_at+interval '1 hour'); RESET ROLE;
    RAISE EXCEPTION 'AC1-N3: obsolete or NULL assignee recorded final end' USING ERRCODE='P9940';
   EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
   ASSERT pg_temp.end_state()=before_state,'AC1-N3: refused assignee changed state';
  END LOOP;

  -- AC1-X4 (cross-cutting): an actual pre-confirmation reschedule invalidates the deadline; equivalent date values retain it.
  before_state:=pg_temp.end_state();
  UPDATE public.event_requests SET proposed_date_times=ARRAY['2026-11-25T10:00:00+08:00'::timestamptz] WHERE id=e;
  ASSERT (SELECT final_event_end_at=end_at FROM public.event_requests WHERE id=e), 'AC1-X4: equal proposed instants erased final end';
  ASSERT pg_temp.end_state()-'events'=before_state-'events','AC1-X4: equal dates changed related state';
  before_state:=pg_temp.end_state();
  before_event:=(SELECT to_jsonb(r) FROM public.event_requests r WHERE id=e);
  UPDATE public.event_requests SET proposed_date_times=ARRAY['2026-11-26T02:00:00Z'::timestamptz] WHERE id=e;
  expected:=before_event||jsonb_build_object('final_event_end_at',NULL,'proposed_date_times',ARRAY['2026-11-26T02:00:00Z'::timestamptz],
    'updated_at',(SELECT updated_at FROM public.event_requests WHERE id=e));
  ASSERT (SELECT final_event_end_at IS NULL AND to_jsonb(r)=expected FROM public.event_requests r WHERE id=e),
   'AC1-X4: actual reschedule retained stale deadline or changed unrelated event fields';
  ASSERT pg_temp.end_state()-ARRAY['events','registration_reviews']=before_state-ARRAY['events','registration_reviews'],
   'AC1-X4: schedule invalidation changed other protected state';
 END LOOP;
 RAISE NOTICE 'PASS AC1-H3 / AC1-P1 / AC1-B5 / AC1-N3 / AC1-X4';

 -- AC1-P2 (partition): every other lifecycle status refuses end recording, preserving all state.
 FOREACH v_status IN ARRAY ARRAY['Draft','Submitted','Under Review','Changes Requested','Safety Review','Confirmed','Completed','Cancelled','Rejected'] LOOP
  INSERT INTO public.event_requests(organiser_id,event_name,status,proposed_date_times,final_event_end_at)
  VALUES(owner_id,'VERIFY40 end write guard',v_status,ARRAY['2026-11-25T02:00:00Z'::timestamptz],end_at) RETURNING id INTO b;
  INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by) VALUES(b,actor,'verify40');
  before_state:=pg_temp.end_state();
  BEGIN
   SET LOCAL ROLE service_role; PERFORM public.set_event_request_final_end(b,actor,end_at+interval '1 hour'); RESET ROLE;
   RAISE EXCEPTION 'AC1-P2: end recorded in protected state %',v_status USING ERRCODE='P9940';
  EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
  ASSERT pg_temp.end_state()=before_state,'AC1-P2: refused state changed protected rows';

  -- AC1-X5 (cross-cutting): a privileged actual schedule/end edit cannot clear or replace a protected Confirmed/terminal deadline.
  -- Hotfix 2 (0086, SCRUM-40 AC9): moving the dates of a Confirmed event is allowed, because it reopens the event
  -- and clears the end; verify_release_1_hotfixes_2.sql covers that. A direct end edit is still refused for Confirmed.
  IF v_status=ANY(ARRAY['Confirmed','Completed','Cancelled','Rejected']) THEN
   FOREACH field IN ARRAY ARRAY['proposed_date_times','final_event_end_at'] LOOP
    CONTINUE WHEN field='proposed_date_times' AND v_status='Confirmed';
    before_state:=pg_temp.end_state();
    BEGIN
     IF field='proposed_date_times' THEN
      UPDATE public.event_requests SET proposed_date_times=ARRAY['2026-11-26T02:00:00Z'::timestamptz] WHERE id=b;
     ELSE
      UPDATE public.event_requests SET final_event_end_at=end_at+interval '1 hour' WHERE id=b;
     END IF;
     RAISE EXCEPTION 'AC1-X5: protected final end edited or invalidated' USING ERRCODE='P9940';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    ASSERT pg_temp.end_state()=before_state,'AC1-X5: refused protected edit changed rows';
   END LOOP;
  END IF;
 END LOOP;
 RAISE NOTICE 'PASS AC1-P2 / AC1-X5';

 -- AC1-N6 (negative): unknown identity refuses without changing any retained event or history.
 before_state:=pg_temp.end_state();
 BEGIN
  SET LOCAL ROLE service_role; PERFORM public.set_event_request_final_end(gen_random_uuid(),actor,end_at); RESET ROLE;
  RAISE EXCEPTION 'AC1-N6: unknown event accepted' USING ERRCODE='P9940';
 EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
 ASSERT pg_temp.end_state()=before_state,'AC1-N6: unknown event changed state';
 RAISE NOTICE 'PASS AC1-N6';

 -- AC3-X2 (cross-cutting): browser roles cannot bypass authenticated coordinator end recording through the native routine.
 FOREACH v_status IN ARRAY ARRAY['anon','authenticated'] LOOP
  ASSERT NOT has_function_privilege(v_status,'public.set_event_request_final_end(uuid,character varying,timestamp with time zone)','EXECUTE'),
   'AC3-X2: browser can execute protected final-end routine';
 END LOOP;
 ASSERT has_function_privilege('service_role','public.set_event_request_final_end(uuid,character varying,timestamp with time zone)','EXECUTE'),
  'AC3-X2: service setter is inaccessible';
 RAISE NOTICE 'PASS AC3-X2 setter grants';
END $cases$;
ROLLBACK;
