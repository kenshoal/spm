-- Shared-safe smoke of existing ACs: fixture-only DML, no Auth/privilege/schema mutation.
-- Run the complete file in ONE privileged connection; roll back that connection on ANY error.
-- Uncommitted jobs are invisible to separate delivery workers. No HTTP sender is called.
BEGIN;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
DO $$
DECLARE
 e uuid := 'f0640000-0000-4000-8000-000000000001';
 v uuid := 'f0640000-0000-4000-8000-000000000002';
 b uuid := 'f0640000-0000-4000-8000-000000000003';
 q uuid := 'f0640000-0000-4000-8000-000000000004';
 req uuid := 'f0640000-0000-4000-8000-000000000005';
 res uuid := 'f0640000-0000-4000-8000-000000000006';
 decision uuid := 'f0640000-0000-4000-8000-000000000007';
 actor uuid; today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
 resources jsonb; lifecycle jsonb; event_protected jsonb; reviews_before jsonb; jobs_before jsonb;
 first_equipment_review jsonb; venue_review public.arrangement_reviews; cleared public.arrangement_reviews;
 expected_ids uuid[]; actual_ids uuid[]; rows_raised integer; history_count bigint; started timestamptz; optional_cause_unused boolean;
BEGIN
 -- Preconditions: never overwrite a collision or alter a real account/role for the fixture.
 ASSERT NOT EXISTS(SELECT 1 FROM public.event_requests WHERE id=e)
  AND NOT EXISTS(SELECT 1 FROM public.venues WHERE id=v)
  AND NOT EXISTS(SELECT 1 FROM public.venue_booking_requests WHERE id=b)
  AND NOT EXISTS(SELECT 1 FROM public.equipment WHERE id=q)
  AND NOT EXISTS(SELECT 1 FROM public.equipment_requirements WHERE id=req)
  AND NOT EXISTS(SELECT 1 FROM public.equipment_reservations WHERE id=res)
  AND NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id=e OR trigger_id=decision OR arrangement_id IN(b,res))
  AND NOT EXISTS(SELECT 1 FROM public.event_request_status_history WHERE event_request_id=e)
  AND NOT EXISTS(SELECT 1 FROM public.event_coordinator_assignments WHERE event_request_id=e)
  AND NOT EXISTS(SELECT 1 FROM public.event_request_outbox WHERE event_request_id=e)
  AND NOT EXISTS(SELECT 1 FROM public.equipment_status_history WHERE equipment_id=q)
  AND NOT EXISTS(SELECT 1 FROM public.arrangement_review_notification_outbox WHERE event_request_id=e),
  'PRECONDITION: shared rollout fixture UUID already exists; abort without cleanup/overwrite';
 IF to_regclass('public.safety_reviews') IS NOT NULL THEN
  EXECUTE 'SELECT NOT EXISTS(SELECT 1 FROM public.safety_reviews WHERE id=$1 OR event_request_id=$2)'
   INTO optional_cause_unused USING decision,e;
  ASSERT optional_cause_unused,'PRECONDITION: optional saved-decision fixture UUID already exists';
 END IF;
 SELECT id INTO actor FROM auth.users ORDER BY id LIMIT 1;
 ASSERT actor IS NOT NULL,'PRECONDITION: existing Auth identity required for FK references only';
 INSERT INTO public.event_requests(id,organiser_id,event_name,status,expected_attendance)
 VALUES(e,actor,'VERIFY SCRUM64 ROLLBACK ONLY shared rollout','Planning',25);
 INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES(v,'VERIFY SCRUM64 ROLLBACK ONLY venue','Test wing',100,'{}','{}',
  ARRAY['theatre']::public.room_layout[],ARRAY['AM']::public.booking_slot[]);
 INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
 VALUES(b,v,actor,e,today,today+1,ARRAY['AM']::public.booking_slot[],'approved',actor,transaction_timestamp());
 INSERT INTO public.equipment(id,type,total_owned_quantity,home_location,created_by)
 VALUES(q,'VERIFY SCRUM64 ROLLBACK ONLY equipment',10,'Test store',actor);
 INSERT INTO public.equipment_requirements(id,event_request_id,equipment_type,quantity,recorded_by)
 VALUES(req,e,'VERIFY SCRUM64 ROLLBACK ONLY equipment',5,actor);
 INSERT INTO public.equipment_reservations(id,equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(res,q,req,e,1,today,today+1,actor);
 SELECT jsonb_build_object('venue',to_jsonb(vr),'booking',to_jsonb(br),'requirement',to_jsonb(er),'reservation',to_jsonb(rr))
 INTO resources FROM public.venues vr,public.venue_booking_requests br,public.equipment_requirements er,public.equipment_reservations rr
 WHERE vr.id=v AND br.id=b AND er.id=req AND rr.id=res;
 SELECT jsonb_agg(to_jsonb(h) ORDER BY id) INTO lifecycle FROM public.event_request_status_history h WHERE event_request_id=e;
 ASSERT jsonb_array_length(lifecycle)=1,'PRECONDITION: nonempty event creation history required';
 SELECT to_jsonb(r)-ARRAY['expected_attendance','description','updated_at'] INTO event_protected FROM public.event_requests r WHERE id=e;

 -- AC1-H1 (happy): accepted significant attendance change flags exact current arrangements without a lifecycle transition.
 SET LOCAL ROLE service_role;
 UPDATE public.event_requests SET expected_attendance=40 WHERE id=e;
 RESET ROLE;
 ASSERT (SELECT count(*)=2 AND count(DISTINCT trigger_id)=1 AND
  bool_and(trigger_type='event_change' AND changed_fields=ARRAY['expected_attendance']
   AND strpos(reason,'25')>0 AND strpos(reason,'40')>0 AND cleared_at IS NULL)
  FROM public.arrangement_reviews WHERE event_request_id=e),'AC1-H1: expected two complete significant-change flags';
 SELECT * INTO STRICT venue_review FROM public.arrangement_reviews WHERE event_request_id=e AND arrangement='venue_booking' AND arrangement_id=b;
 SELECT to_jsonb(r) INTO first_equipment_review FROM public.arrangement_reviews r WHERE event_request_id=e AND arrangement='equipment_reservation' AND arrangement_id=res;
 ASSERT first_equipment_review IS NOT NULL,'AC1-H1: missing linked reservation review';

 -- AC3-P1 (partition): each raised review atomically enqueues its complete immutable evidence, without claiming delivery.
 ASSERT (SELECT count(*)=2 AND bool_and(j.payload=(to_jsonb(r)-'id')||jsonb_build_object('review_id',r.id)
  AND j.published_at IS NULL AND j.accepted_recipients='{}'::jsonb)
  FROM public.arrangement_reviews r JOIN public.arrangement_review_notification_outbox j ON j.review_id=r.id
  WHERE r.event_request_id=e AND j.event_request_id=e),'AC3-P1: incomplete, missing or prematurely delivered work';
 SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO reviews_before FROM public.arrangement_reviews r WHERE event_request_id=e;
 SELECT jsonb_agg(to_jsonb(j) ORDER BY review_id) INTO jobs_before FROM public.arrangement_review_notification_outbox j WHERE event_request_id=e;

 -- AC2-N1 (negative): an unchanged significant value and unrelated description cannot raise new review work.
 SET LOCAL ROLE service_role;
 UPDATE public.event_requests SET expected_attendance=40,description='VERIFY unrelated description only' WHERE id=e;
 RESET ROLE;
 ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r WHERE event_request_id=e)=reviews_before
  AND (SELECT jsonb_agg(to_jsonb(j) ORDER BY review_id) FROM public.arrangement_review_notification_outbox j WHERE event_request_id=e)=jobs_before,
  'AC2-N1: no-op/unrelated change altered reviews or pending work';

 -- AC6-H1 (happy): the real status RPC adds an exact reserved-equipment cause and its normal audit while preserving older evidence.
 SELECT count(*) INTO history_count FROM public.equipment_status_history WHERE equipment_id=q;
 SET LOCAL ROLE service_role;
 PERFORM public.transition_equipment_status(q,'DAMAGED'::varchar,actor,'VERIFY SCRUM64 shared rollback smoke');
 RESET ROLE;
 ASSERT (SELECT operational_status='DAMAGED' FROM public.equipment WHERE id=q)
  AND (SELECT count(*)=history_count+1 FROM public.equipment_status_history WHERE equipment_id=q),
  'AC6-H1: normal equipment status/audit did not change';
 ASSERT (SELECT count(*)=1 AND bool_and(arrangement='equipment_reservation' AND arrangement_id=res
  AND changed_fields=ARRAY['operational_status'] AND strpos(reason,'AVAILABLE')>0 AND strpos(reason,'DAMAGED')>0)
  FROM public.arrangement_reviews WHERE event_request_id=e AND trigger_type='equipment_unavailable'),
  'AC6-H1: unavailable equipment missing or incorrectly targeted';
 ASSERT (SELECT to_jsonb(r) FROM public.arrangement_reviews r WHERE id=(first_equipment_review->>'id')::uuid)=first_equipment_review,
  'AC6-H1: later cause changed the original reservation review';

 -- AC4-H1 (happy): trusted server-domain clear changes only the exact older review audit pair, not another cause.
 started:=clock_timestamp();
 SET LOCAL ROLE service_role;
 SELECT * INTO cleared FROM public.clear_arrangement_review((first_equipment_review->>'id')::uuid,actor,ARRAY['equipment_reservation']);
 RESET ROLE;
 ASSERT cleared.cleared_by=actor AND cleared.cleared_at BETWEEN started AND clock_timestamp()
  AND (to_jsonb(cleared)-ARRAY['cleared_at','cleared_by'])=(first_equipment_review-ARRAY['cleared_at','cleared_by']),
  'AC4-H1: exact audit or prior evidence mismatch';
 ASSERT (SELECT count(*)=1 AND bool_and(cleared_at IS NULL) FROM public.arrangement_reviews WHERE event_request_id=e AND trigger_type='equipment_unavailable'),
  'AC4-H1: clearing the old cause also cleared the newer one';

 -- AC7-H1 (happy): explicit trusted-helper targets share a supplied test cause without making a saved-decision/auth claim.
 PERFORM 1 FROM public.event_requests WHERE id=e FOR UPDATE;
 rows_raised:=private.raise_safety_arrangement_reviews(e,decision,
  jsonb_build_array(jsonb_build_object('arrangement','venue_booking','id',b),jsonb_build_object('arrangement','equipment_reservation','id',res)),
  'VERIFY explicit safety recheck for both arrangements');
 ASSERT rows_raised=2 AND (SELECT count(*)=2 AND bool_and(reason='VERIFY explicit safety recheck for both arrangements' AND cleared_at IS NULL)
  FROM public.arrangement_reviews WHERE event_request_id=e AND trigger_type='safety_recheck' AND trigger_id=decision),
  'AC7-H1: explicit target/cause/reason mismatch';
 SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO reviews_before FROM public.arrangement_reviews r WHERE event_request_id=e;
 SELECT jsonb_agg(to_jsonb(j) ORDER BY review_id) INTO jobs_before FROM public.arrangement_review_notification_outbox j WHERE event_request_id=e;

 -- AC3-N1 (negative): exact helper replay must neither replace raised evidence nor enqueue another delivery job.
 rows_raised:=private.raise_safety_arrangement_reviews(e,decision,
  jsonb_build_array(jsonb_build_object('arrangement','venue_booking','id',b),jsonb_build_object('arrangement','equipment_reservation','id',res)),
  'A replay must not replace the original reason');
 ASSERT rows_raised=0 AND (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r WHERE event_request_id=e)=reviews_before
  AND (SELECT jsonb_agg(to_jsonb(j) ORDER BY review_id) FROM public.arrangement_review_notification_outbox j WHERE event_request_id=e)=jobs_before,
  'AC3-N1: replay rewrote evidence or duplicated work';

 -- AC5-X2 (cross-cutting): shared outstanding facts agree with exact persisted rows, while lifecycle and arrangement records stay unchanged.
 SELECT array_agg(id ORDER BY raised_at DESC,id DESC) INTO expected_ids FROM public.arrangement_reviews WHERE event_request_id=e AND cleared_at IS NULL;
 SET LOCAL ROLE service_role;
 SELECT array_agg(id ORDER BY raised_at DESC,id DESC) INTO actual_ids FROM public.get_outstanding_arrangement_reviews(e);
 RESET ROLE;
 ASSERT cardinality(expected_ids)=4 AND actual_ids=expected_ids,'AC5-X2: shared outstanding list differs from persisted truth';
 ASSERT (SELECT count(*)=5 AND bool_and(published_at IS NULL AND accepted_recipients='{}'::jsonb)
  FROM public.arrangement_review_notification_outbox WHERE event_request_id=e),'AC3-P1: final pending work count/progress mismatch';
 ASSERT (SELECT jsonb_agg(to_jsonb(h) ORDER BY id) FROM public.event_request_status_history h WHERE event_request_id=e)=lifecycle
  AND (SELECT to_jsonb(r)-ARRAY['expected_attendance','description','updated_at'] FROM public.event_requests r WHERE id=e)=event_protected,
  'AC5-X2: event lifecycle/history or protected event fields changed';
 ASSERT (SELECT jsonb_build_object('venue',to_jsonb(vr),'booking',to_jsonb(br),'requirement',to_jsonb(er),'reservation',to_jsonb(rr))
  FROM public.venues vr,public.venue_booking_requests br,public.equipment_requirements er,public.equipment_reservations rr
  WHERE vr.id=v AND br.id=b AND er.id=req AND rr.id=res)=resources,'AC5-X2: venue, booking, requirement or reservation changed';
 RAISE NOTICE 'SCRUM64 shared rollout smoke PASSED; fixture DML will now roll back; no role, saved-decision or HTTP delivery proof';
END $$;
ROLLBACK;
SELECT 'SCRUM64 shared rollout smoke PASSED and ROLLBACK completed' AS verification;
