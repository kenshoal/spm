-- SCRUM-35 date-approval prerequisite; no date approval is activated.
-- Owned disposable database only: real SQL state/privileges, no Auth/JWT claim.
BEGIN;
SET LOCAL statement_timeout='15s';
SET LOCAL lock_timeout='2s';
DO $$ BEGIN
 ASSERT current_database() ~ '^scrum48_', 'Owned disposable scrum48_* database required';
END $$;
CREATE FUNCTION pg_temp.booking_creation_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
 'events',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_requests x),
 'changes',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_change_requests x),
 'assignments',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_coordinator_assignments x),
 'history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_status_history x),
 'venues',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venues x),
 'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.venue_booking_requests x),
 'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.arrangement_reviews x),
 'jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x),
 'submission_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_outbox x),
 'inbox',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.notifications x));
$$;
DO $cases$
DECLARE
 owner_id uuid; e uuid:=gen_random_uuid(); other uuid:=gen_random_uuid();
 venue uuid:=gen_random_uuid(); other_venue uuid:=gen_random_uuid(); bid uuid:=gen_random_uuid();
 actor uuid:=gen_random_uuid(); old_actor uuid:=gen_random_uuid(); version timestamptz;
 payload jsonb; candidate jsonb; saved public.venue_booking_requests; original jsonb;
 before_state jsonb; after_state jsonb; reason text; mutation text; browser text;
BEGIN
 SELECT id INTO owner_id FROM auth.users ORDER BY id LIMIT 1;
 ASSERT owner_id IS NOT NULL, 'SETUP: existing disposable Auth FK fixture required';
 INSERT INTO public.event_requests(id,organiser_id,status,event_name,expected_attendance,venue_requirements)
 VALUES(e,owner_id,'Submitted','Current stored event',55,'Stored stage requirement'),
       (other,owner_id,'Approved','Other event',20,'Other requirement');
 INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
 VALUES(e,old_actor::text,'verify35'),(e,actor::text,'verify35'),(other,actor::text,'verify35');
 INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES(venue,'VERIFY35 versioned creation','Test wing',100,'{}','{}','{theatre}','{AM}'),
       (other_venue,'VERIFY35 other venue','Test wing',100,'{}','{}','{theatre}','{AM}');
 SELECT updated_at INTO version FROM public.event_requests WHERE id=e;
 payload:=jsonb_build_object('id',bid,'venue_id',venue,'requested_by',actor,'event_request_id',e,
  'event_name','Obsolete snapshot name','expected_attendance',1,'requirements_note','Obsolete note',
  'start_date','2030-01-10','end_date','2030-01-11','start_minute',600,'end_minute',720,'slots',jsonb_build_array('AM'),
  'status','pending','decision_reason',NULL,'suggested_alternative',NULL,'decided_by',NULL,'decided_at',NULL,
  'cancelled_by',NULL,'cancelled_at',NULL,'created_at',transaction_timestamp());

 -- AC3-X14 (cross-cutting): direct table insertion must not bypass the version/assignment boundary.
 before_state:=pg_temp.booking_creation_state();
 BEGIN
  SET LOCAL ROLE service_role;
  INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,start_minute,end_minute,slots,status)
  VALUES(bid,venue,actor,e,'2030-01-10','2030-01-11',600,720,'{AM}','pending');
  RESET ROLE;
  RAISE EXCEPTION 'AC3-X14: legacy direct INSERT bypassed versioned creation' USING ERRCODE='P9914';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 ASSERT pg_temp.booking_creation_state()=before_state, 'AC3-X14: refused direct INSERT changed state';
 ASSERT NOT has_table_privilege('service_role','public.venue_booking_requests','DELETE'), 'AC3-X14: direct DELETE still granted';
 ASSERT to_regprocedure('public.create_event_venue_booking_request(jsonb,timestamp with time zone)') IS NOT NULL,
  'SETUP: reviewed versioned creation RPC required for the remaining assertions';

 -- AC3-X15 (cross-cutting): the current assigned actor and instant-equal version create only one Pending row with canonical stored event metadata.
 before_state:=pg_temp.booking_creation_state();
 SET LOCAL ROLE service_role;
 saved:=public.create_event_venue_booking_request(payload,version AT TIME ZONE 'UTC' AT TIME ZONE 'UTC');
 RESET ROLE;
 ASSERT saved.id=bid AND saved.venue_id=venue AND saved.event_request_id=e AND saved.requested_by=actor
  AND saved.status='pending' AND saved.event_name='Current stored event' AND saved.expected_attendance=55
  AND saved.requirements_note='Stored stage requirement', 'AC3-X15: identity/actor/Pending/current metadata incorrect';
 ASSERT saved.start_date='2030-01-10'::date AND saved.end_date='2030-01-11'::date
  AND saved.start_minute=600 AND saved.end_minute=720 AND saved.slots=ARRAY['AM'::public.booking_slot]
  AND saved.decided_by IS NULL AND saved.decided_at IS NULL AND saved.decision_reason IS NULL
  AND saved.suggested_alternative IS NULL AND saved.cancelled_by IS NULL AND saved.cancelled_at IS NULL
  AND saved.created_at=transaction_timestamp(), 'AC3-X15: requested booking/audit fields changed';
 ASSERT (SELECT to_jsonb(x)=to_jsonb(saved) FROM public.venue_booking_requests x WHERE id=bid), 'AC3-X15: returned row not persisted';
 after_state:=pg_temp.booking_creation_state();
 ASSERT after_state-'bookings'=before_state-'bookings', 'AC3-X15: creation changed event/lifecycle/review/notification state';
 ASSERT (SELECT coalesce(jsonb_agg(x ORDER BY x->>'id'),'[]') FROM jsonb_array_elements(after_state->'bookings') x WHERE x->>'id'<>bid::text)
  =before_state->'bookings', 'AC3-X15: creation changed another booking';
 original:=to_jsonb(saved);

 -- AC3-N18, AC2-N7, AC2-N8 (negative): stale snapshots, missing events and replaced assignees cannot insert or mutate protected state.
 FOREACH reason IN ARRAY ARRAY['stale','missing','reassigned'] LOOP
  candidate:=payload||jsonb_build_object('id',gen_random_uuid());
  IF reason='missing' THEN candidate:=candidate||jsonb_build_object('event_request_id',gen_random_uuid()); END IF;
  IF reason='reassigned' THEN candidate:=candidate||jsonb_build_object('requested_by',old_actor); END IF;
  before_state:=pg_temp.booking_creation_state();
  BEGIN
   SET LOCAL ROLE service_role;
   PERFORM public.create_event_venue_booking_request(candidate,CASE WHEN reason='stale' THEN version-interval '1 second' ELSE version END);
   RESET ROLE;
   RAISE EXCEPTION 'AC3-N18/AC2-N7/AC2-N8: invalid creation accepted (%)',reason USING ERRCODE='P9915';
  EXCEPTION WHEN SQLSTATE 'P0004' THEN IF reason<>'stale' THEN RAISE; END IF;
   WHEN SQLSTATE 'P0002' THEN IF reason<>'missing' THEN RAISE; END IF;
   WHEN SQLSTATE 'P0003' THEN IF reason<>'reassigned' THEN RAISE; END IF;
  END;
  ASSERT pg_temp.booking_creation_state()=before_state, 'AC3-N18/AC2-N7/AC2-N8: refused creation changed state';
 END LOOP;

 -- AC3-N19 (negative): a server payload cannot smuggle an already-approved outcome or decision audit into creation.
 before_state:=pg_temp.booking_creation_state();
 BEGIN
  SET LOCAL ROLE service_role;
  PERFORM public.create_event_venue_booking_request(payload||jsonb_build_object('id',gen_random_uuid(),'status','approved',
   'decided_by',actor,'decided_at',transaction_timestamp()),version);
  RESET ROLE;
  RAISE EXCEPTION 'AC3-N19: supplied approval outcome accepted during creation' USING ERRCODE='P9919';
 EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
 ASSERT pg_temp.booking_creation_state()=before_state, 'AC3-N19: invalid creation audit changed state';

 -- AC3-X16 (cross-cutting): immutable membership rejects changed or null event/venue links while harmless same-value updates remain possible.
 FOREACH mutation IN ARRAY ARRAY['event','venue','null_event','null_venue'] LOOP
  before_state:=pg_temp.booking_creation_state();
  BEGIN
   SET LOCAL ROLE service_role;
   UPDATE public.venue_booking_requests SET
    event_request_id=CASE WHEN mutation='event' THEN other WHEN mutation='null_event' THEN NULL ELSE event_request_id END,
    venue_id=CASE WHEN mutation='venue' THEN other_venue WHEN mutation='null_venue' THEN NULL ELSE venue_id END
   WHERE id=bid;
   RESET ROLE;
   RAISE EXCEPTION 'AC3-X16: booking membership change accepted (%)',mutation USING ERRCODE='P9916';
  EXCEPTION WHEN SQLSTATE '22023' THEN
   ASSERT SQLERRM='Booking event and venue cannot be changed', 'AC3-X16: wrong membership refusal';
  END;
  ASSERT pg_temp.booking_creation_state()=before_state, 'AC3-X16: refused membership change mutated state';
 END LOOP;
 SET LOCAL ROLE service_role;
 UPDATE public.venue_booking_requests SET venue_id=venue_id,event_request_id=event_request_id WHERE id=bid;
 RESET ROLE;
 ASSERT (SELECT to_jsonb(x)=original FROM public.venue_booking_requests x WHERE id=bid), 'AC3-X16: same-value update rewrote booking';

 -- AC3-X14 (cross-cutting): neither browser role can invoke the server-only creation function or delete its row.
 FOREACH browser IN ARRAY ARRAY['anon','authenticated'] LOOP
  ASSERT NOT has_function_privilege(browser,'public.create_event_venue_booking_request(jsonb,timestamp with time zone)','EXECUTE'),
   'AC3-X14: browser execute privilege exposed';
  before_state:=pg_temp.booking_creation_state();
  BEGIN
   EXECUTE format('SET LOCAL ROLE %I',browser);
   PERFORM public.create_event_venue_booking_request(payload,version); RESET ROLE;
   RAISE EXCEPTION 'AC3-X14: browser creation executed' USING ERRCODE='P9917';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  ASSERT pg_temp.booking_creation_state()=before_state, 'AC3-X14: browser refusal mutated state';
 END LOOP;
 before_state:=pg_temp.booking_creation_state();
 BEGIN
  SET LOCAL ROLE service_role; DELETE FROM public.venue_booking_requests WHERE id=bid; RESET ROLE;
  RAISE EXCEPTION 'AC3-X14: direct service DELETE executed' USING ERRCODE='P9918';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 ASSERT pg_temp.booking_creation_state()=before_state, 'AC3-X14: refused DELETE changed state';
 ASSERT has_function_privilege('service_role','public.create_event_venue_booking_request(jsonb,timestamp with time zone)','EXECUTE'),
  'AC3-X14: server execute missing';
 RAISE NOTICE 'SCRUM35 versioned venue booking creation verification PASSED';
END $cases$;
ROLLBACK;
