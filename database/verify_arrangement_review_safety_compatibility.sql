-- AC5-X7 (cross-cutting): upstream Safety Review schema and renumbered SCRUM64 writes coexist without lifecycle changes.
-- Disposable PostgreSQL only: exact upstream0029, review0030-0033 and README prerequisites.
-- Run psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_safety_compatibility.sql.
BEGIN;
GRANT SELECT, UPDATE ON public.equipment TO service_role;
GRANT SELECT, INSERT ON public.equipment_status_history TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.equipment_status_history_id_seq TO service_role;
DO $$
DECLARE
 v_actor uuid;
 v_event uuid;
 v_venue uuid;
 v_booking uuid;
 v_equipment uuid;
 v_requirement uuid;
 v_reservation uuid;
 v_venue_review public.arrangement_reviews;
 v_cleared public.arrangement_reviews;
 v_today date:=(transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
 v_resources jsonb;
 v_after_resources jsonb;
 v_lifecycle jsonb;
 v_old_equipment_review jsonb;
 v_before_clear timestamptz;
BEGIN
 SELECT id INTO v_actor FROM auth.users ORDER BY id LIMIT 1;
 ASSERT v_actor IS NOT NULL, 'fixture: disposable auth identity required';
 INSERT INTO public.event_requests(organiser_id,event_name,status,expected_attendance)
 VALUES(v_actor,'VERIFY SCRUM64 Safety Review compatibility','Safety Review',25)
 RETURNING id INTO v_event;
 INSERT INTO public.venues
  (name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
 VALUES('VERIFY SCRUM64 safety venue','Test wing',100,'{}','{}',
  ARRAY['theatre']::public.room_layout[],ARRAY['AM']::public.booking_slot[])
 RETURNING id INTO v_venue;
 INSERT INTO public.venue_booking_requests
  (venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
 VALUES(v_venue,v_actor,v_event,v_today-1,v_today,ARRAY['AM']::public.booking_slot[],
  'approved',v_actor,transaction_timestamp()) RETURNING id INTO v_booking;
 INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
 VALUES('VERIFY SCRUM64 safety microphone',10,'Test store',v_actor) RETURNING id INTO v_equipment;
 INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
 VALUES(v_event,'VERIFY SCRUM64 safety microphone',10,v_actor) RETURNING id INTO v_requirement;
 INSERT INTO public.equipment_reservations
  (equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
 VALUES(v_equipment,v_requirement,v_event,1,v_today-1,v_today,v_actor) RETURNING id INTO v_reservation;
 SELECT jsonb_build_object('booking',to_jsonb(b),'reservation',to_jsonb(r),'requirement',to_jsonb(q))
 INTO v_resources FROM public.venue_booking_requests b,public.equipment_reservations r,
  public.equipment_requirements q WHERE b.id=v_booking AND r.id=v_reservation AND q.id=v_requirement;
 SELECT jsonb_agg(to_jsonb(h) ORDER BY id) INTO v_lifecycle
 FROM public.event_request_status_history h WHERE event_request_id=v_event;
 ASSERT jsonb_array_length(v_lifecycle)=1, 'AC5-X7: nonempty creation lifecycle evidence required';

 -- AC1-H1 (happy/compatibility): Safety Review is nonterminal for significant accepted arrangement changes.
 SET LOCAL ROLE service_role;
 UPDATE public.event_requests SET expected_attendance=40 WHERE id=v_event;
 RESET ROLE;
 ASSERT (SELECT count(*)=2 AND count(DISTINCT trigger_id)=1
  AND bool_and(trigger_type='event_change' AND changed_fields=ARRAY['expected_attendance']
   AND strpos(reason,'25')>0 AND strpos(reason,'40')>0 AND cleared_at IS NULL)
  FROM public.arrangement_reviews WHERE event_request_id=v_event),
  'AC5-X7/AC1-H1: Safety Review significant change did not flag both domains';
 SELECT * INTO STRICT v_venue_review FROM public.arrangement_reviews
  WHERE event_request_id=v_event AND arrangement='venue_booking' AND arrangement_id=v_booking;
 SELECT to_jsonb(r) INTO v_old_equipment_review FROM public.arrangement_reviews r
  WHERE event_request_id=v_event AND arrangement='equipment_reservation' AND arrangement_id=v_reservation;
 ASSERT v_old_equipment_review IS NOT NULL, 'AC5-X7: missing actual reservation target';

 -- AC4-H1 (happy/compatibility): authorised domain clearing records audit without a Safety Review lifecycle decision.
 v_before_clear:=clock_timestamp();
 SET LOCAL ROLE service_role;
 SELECT * INTO v_cleared FROM public.clear_arrangement_review(v_venue_review.id,v_actor,ARRAY['venue_booking']);
 RESET ROLE;
 ASSERT v_cleared.cleared_by=v_actor AND v_cleared.cleared_at>=v_before_clear
  AND v_cleared.cleared_at<=clock_timestamp()
  AND (to_jsonb(v_cleared)-ARRAY['cleared_at','cleared_by'])=
      (to_jsonb(v_venue_review)-ARRAY['cleared_at','cleared_by']),
  'AC5-X7/AC4-H1: exact Safety Review clear audit/evidence mismatch';

 -- AC6-H1 (happy/compatibility): unavailable reserved equipment still raises work in Safety Review without auto-clearing prior causes.
 SET LOCAL ROLE service_role;
 PERFORM public.transition_equipment_status(v_equipment,'DAMAGED'::varchar,v_actor,'VERIFY Safety Review unavailable');
 RESET ROLE;
 ASSERT (SELECT count(*)=1 AND bool_and(arrangement='equipment_reservation'
  AND arrangement_id=v_reservation AND trigger_type='equipment_unavailable'
  AND changed_fields=ARRAY['operational_status'] AND strpos(reason,'AVAILABLE')>0
  AND strpos(reason,'DAMAGED')>0 AND cleared_at IS NULL AND cleared_by IS NULL)
  FROM public.arrangement_reviews WHERE event_request_id=v_event AND trigger_type='equipment_unavailable'),
  'AC5-X7/AC6-H1: Safety Review equipment cause absent or incorrectly targeted';
 ASSERT (SELECT to_jsonb(r) FROM public.arrangement_reviews r
  WHERE id=(v_old_equipment_review->>'id')::uuid)=v_old_equipment_review,
  'AC5-X7: later unavailability changed prior equipment review';
 ASSERT (SELECT count(*)=2 FROM public.arrangement_reviews WHERE event_request_id=v_event AND cleared_at IS NULL),
  'AC5-X7: outstanding truth lost original or later cause';
 ASSERT (SELECT to_jsonb(r) FROM public.arrangement_reviews r WHERE id=v_cleared.id)=to_jsonb(v_cleared),
  'AC5-X7: subsequent flag changed completed domain audit';
 ASSERT (SELECT status='Safety Review' AND expected_attendance=40 FROM public.event_requests WHERE id=v_event),
  'AC5-X7: arrangement work changed the event lifecycle';
 ASSERT (SELECT jsonb_agg(to_jsonb(h) ORDER BY id) FROM public.event_request_status_history h
  WHERE event_request_id=v_event)=v_lifecycle, 'AC5-X7: non-lifecycle work appended/changed lifecycle history';
 SELECT jsonb_build_object('booking',to_jsonb(b),'reservation',to_jsonb(r),'requirement',to_jsonb(q))
 INTO v_after_resources FROM public.venue_booking_requests b,public.equipment_reservations r,
  public.equipment_requirements q WHERE b.id=v_booking AND r.id=v_reservation AND q.id=v_requirement;
 ASSERT v_after_resources=v_resources, 'AC5-X7: flag/clear rewrote arrangement details or resource status';
 ASSERT (SELECT operational_status='DAMAGED' FROM public.equipment WHERE id=v_equipment)
  AND (SELECT count(*)=1 FROM public.equipment_status_history
   WHERE equipment_id=v_equipment AND old_status='AVAILABLE' AND new_status='DAMAGED' AND changed_by=v_actor),
  'AC5-X7: permitted operational update/audit did not persist';
 RAISE NOTICE 'AC5-X7 Safety Review arrangement compatibility PASSED';
END $$;
ROLLBACK;
