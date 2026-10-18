-- SCRUM64/SCRUM61 compatibility: ordinary accepted changes exclude cancelled bookings.
-- Disposable PostgreSQL only; real0030–0038/0040 and separate0041 then0042 prerequisites.
-- psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_cancelled_venues.sql
-- Explicit AC7 targeting remains unfiltered; cancellation is not an acknowledgement.
BEGIN;
DO $$
DECLARE
 actor uuid; event_id uuid; venue_id uuid; cancelled_id uuid; sibling_id uuid;
 equipment_id uuid; requirement_id uuid; reservation_id uuid; original_review uuid;
 original_cause uuid:=gen_random_uuid(); today date:=(transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
 before_review jsonb; before_job jsonb; before_reviews jsonb; before_jobs jsonb;
 before_history jsonb; before_notifications jsonb; before_submission jsonb;
 before_sibling jsonb; before_reservation jsonb; before_requirement jsonb; before_equipment jsonb;
 cancelled_row jsonb; actual_cancel jsonb; cancelled_at timestamptz;
 rows jsonb; fresh_cause uuid;
BEGIN
 ASSERT to_regprocedure('public.cancel_venue_booking_request(uuid,uuid)') IS NOT NULL,
 'setup: actual SCRUM61 cancellation RPC0042 required';
 SELECT id INTO actor FROM auth.users ORDER BY id LIMIT 1;
 ASSERT actor IS NOT NULL,'setup: disposable identity required';
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(actor,'VERIFY SCRUM64 cancelled venue compatibility','Planning',25) RETURNING id INTO event_id;
 INSERT INTO public.venues(name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES('SCRUM64 cancelled/sibling venue','Test wing',100,'{}','{}','{theatre}','{AM,PM}') RETURNING id INTO venue_id;
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
 VALUES(venue_id,actor,event_id,today,today+1,'{AM}','approved',actor,now()) RETURNING id INTO cancelled_id;
 INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
 VALUES(venue_id,actor,event_id,today,today+1,'{PM}','approved',actor,now()) RETURNING id INTO sibling_id;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('SCRUM64 cancellation microphone',10,'Test store',actor) RETURNING id INTO equipment_id;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(event_id,'SCRUM64 cancellation microphone',1,actor) RETURNING id INTO requirement_id;
 INSERT INTO public.equipment_reservations(equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(equipment_id,requirement_id,event_id,1,today,today+1,actor) RETURNING id INTO reservation_id;
 INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
 VALUES(event_id,'venue_booking',cancelled_id,original_cause,'event_change',ARRAY['venue_requirements'],
 'Existing review: retain original room access evidence') RETURNING id INTO original_review;
 SELECT to_jsonb(r) INTO before_review FROM public.arrangement_reviews r WHERE id=original_review;
 SELECT to_jsonb(j) INTO before_job FROM public.arrangement_review_notification_outbox j WHERE review_id=original_review;
 SELECT jsonb_agg(to_jsonb(r) ORDER BY id) INTO before_reviews FROM public.arrangement_reviews r WHERE event_request_id=event_id;
 SELECT jsonb_agg(to_jsonb(j) ORDER BY review_id) INTO before_jobs FROM public.arrangement_review_notification_outbox j WHERE event_request_id=event_id;
 SELECT to_jsonb(b) INTO before_sibling FROM public.venue_booking_requests b WHERE id=sibling_id;
 SELECT to_jsonb(r) INTO before_reservation FROM public.equipment_reservations r WHERE id=reservation_id;
 SELECT to_jsonb(q) INTO before_requirement FROM public.equipment_requirements q WHERE id=requirement_id;
 SELECT to_jsonb(e) INTO before_equipment FROM public.equipment e WHERE id=equipment_id;
 SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY id),'[]') INTO before_history FROM public.event_request_status_history h;
 SELECT coalesce(jsonb_agg(to_jsonb(n) ORDER BY id),'[]') INTO before_notifications FROM public.notifications n;
 SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY id),'[]') INTO before_submission FROM public.event_request_outbox o;

 -- AC1-P3 (partition): cancelled bookings receive no new ordinary change flags, while eligible controls and old evidence remain correct.
 SET LOCAL ROLE service_role;
 actual_cancel:=public.cancel_venue_booking_request(cancelled_id,actor);
 RESET ROLE;
 SELECT to_jsonb(b) INTO cancelled_row FROM public.venue_booking_requests b WHERE id=cancelled_id;
 cancelled_at:=(cancelled_row->>'cancelled_at')::timestamptz;
 ASSERT actual_cancel=cancelled_row AND cancelled_row->>'status'='cancelled'
 AND cancelled_row->>'cancelled_by'=actor::text AND cancelled_at>=transaction_timestamp() AND cancelled_at<=clock_timestamp(),
 'AC1-P3 setup: actual cancellation did not persist its exact row/audit';
 ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.arrangement_reviews r WHERE event_request_id=event_id)=before_reviews
 AND (SELECT jsonb_agg(to_jsonb(j) ORDER BY review_id) FROM public.arrangement_review_notification_outbox j WHERE event_request_id=event_id)=before_jobs,
 'AC1-P3: cancellation auto-cleared/rewrote review evidence or created arrangement delivery work';
 SET LOCAL ROLE service_role;
 UPDATE public.event_requests SET expected_attendance=40 WHERE id=event_id;
 RESET ROLE;
 ASSERT (SELECT count(*)=3 FROM public.arrangement_reviews WHERE event_request_id=event_id),
 'AC1-P3: expected retained cancelled review plus exactly two eligible new flags';
 ASSERT (SELECT count(*)=1 FROM public.arrangement_reviews WHERE arrangement='venue_booking' AND arrangement_id=cancelled_id),
 'AC1-P3: ordinary event change raised new work for cancelled booking';
 SELECT trigger_id INTO fresh_cause FROM public.arrangement_reviews WHERE arrangement='venue_booking' AND arrangement_id=sibling_id;
 ASSERT fresh_cause IS NOT NULL AND fresh_cause<>original_cause,
 'AC1-P3: approved sibling failed to receive a distinct current cause';
 ASSERT (SELECT count(*)=2 AND bool_and(trigger_id=fresh_cause AND trigger_type='event_change'
  AND changed_fields=ARRAY['expected_attendance'] AND reason LIKE '%25%' AND reason LIKE '%40%'
  AND cleared_at IS NULL AND cleared_by IS NULL
  AND ((arrangement='venue_booking' AND arrangement_id=sibling_id)
    OR(arrangement='equipment_reservation' AND arrangement_id=reservation_id)))
 FROM public.arrangement_reviews WHERE event_request_id=event_id AND id<>original_review),
 'AC1-P3: eligible sibling/equipment lost target, shared cause, actual change or clear state';
 ASSERT (SELECT to_jsonb(r) FROM public.arrangement_reviews r WHERE id=original_review)=before_review
 AND (SELECT to_jsonb(j) FROM public.arrangement_review_notification_outbox j WHERE review_id=original_review)=before_job,
 'AC1-P3: old cancelled-booking review/job evidence changed';
 ASSERT (SELECT count(*)=3 AND count(*) FILTER(WHERE published_at IS NULL)=3
 FROM public.arrangement_review_notification_outbox WHERE event_request_id=event_id),
 'AC1-P3: missing eligible enqueue or spurious cancellation enqueue';
 SET LOCAL ROLE service_role;
 SELECT jsonb_agg(to_jsonb(r)) INTO rows FROM public.get_outstanding_arrangement_reviews(event_id) r;
 RESET ROLE;
 ASSERT jsonb_array_length(rows)=3 AND rows @> jsonb_build_array(before_review),
 'AC1-P3: coordinator shared facts hid or changed earlier uncleared cancellation evidence';
 ASSERT (SELECT count(*)=2 FROM public.arrangement_reviews WHERE event_request_id=event_id
 AND arrangement='venue_booking' AND cleared_at IS NULL),
 'AC1-P3: domain queue storage lost old venue work or sibling review';
 ASSERT (SELECT to_jsonb(b) FROM public.venue_booking_requests b WHERE id=cancelled_id)=cancelled_row
 AND (SELECT to_jsonb(b) FROM public.venue_booking_requests b WHERE id=sibling_id)=before_sibling
 AND (SELECT to_jsonb(r) FROM public.equipment_reservations r WHERE id=reservation_id)=before_reservation
 AND (SELECT to_jsonb(q) FROM public.equipment_requirements q WHERE id=requirement_id)=before_requirement
 AND (SELECT to_jsonb(e) FROM public.equipment e WHERE id=equipment_id)=before_equipment,
 'AC1-P3: ordinary flagging rewrote cancelled/sibling bookings or resource facts';
 ASSERT (SELECT status='Planning' AND expected_attendance=40 FROM public.event_requests WHERE id=event_id)
 AND (SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY id),'[]') FROM public.event_request_status_history h)=before_history
 AND (SELECT coalesce(jsonb_agg(to_jsonb(n) ORDER BY id),'[]') FROM public.notifications n)=before_notifications
 AND (SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY id),'[]') FROM public.event_request_outbox o)=before_submission,
 'AC1-P3: cancellation/detail flagging changed lifecycle, inbox or submission delivery';
 RAISE NOTICE 'AC1-P3 cancelled venue compatibility PASSED (actual cancel RPC; no auto-clear or Auth claim)';
END $$;
ROLLBACK;
