-- SCRUM64 AC4: exact-ID server-authorised clear; real SQL, all fixtures rolled back.
-- Missing public RPC is an execution precondition, not claimed behavioural Red.
-- Run after read0029/flags0030/clear0031 with psql -X -v ON_ERROR_STOP=1 -f <file>.
BEGIN;
CREATE FUNCTION pg_temp.scrum64_fail_clear() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.id::text=current_setting('scrum64.fail_clear_id',true) THEN
        RAISE EXCEPTION 'SCRUM64 injected clear failure' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER scrum64_test_clear_fault BEFORE UPDATE ON public.arrangement_reviews
    FOR EACH ROW EXECUTE FUNCTION pg_temp.scrum64_fail_clear();

CREATE FUNCTION pg_temp.scrum64_clear_state() RETURNS jsonb LANGUAGE sql STABLE AS $$
SELECT jsonb_build_object(
    'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.arrangement_reviews r),
    'events',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_requests r),
    'bookings',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.venue_booking_requests r),
    'reservations',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_reservations r),
    'equipment',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment r),
    'requirements',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.equipment_requirements r),
    'history',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_status_history r),
    'notifications',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.notifications r),
    'outbox',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY id),'[]') FROM public.event_request_outbox r)
);
$$;
DO $$
DECLARE
    v_original uuid;
    v_staff uuid := '64000000-0000-4000-8000-000000000001';
    v_tech uuid := '64000000-0000-4000-8000-000000000002';
    v_event uuid; v_venue uuid; v_booking uuid; v_equipment uuid;
    v_requirement uuid; v_reservation uuid; v_t1 uuid; v_t2 uuid; v_t3 uuid; v_eq uuid;
    v_today date := (transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
    v_loaded jsonb; v_expected jsonb; v_before jsonb; v_after jsonb; v_newer jsonb;
    v_row public.arrangement_reviews;
    v_start timestamptz; v_end timestamptz; v_message text;
    v_function oid := to_regprocedure('public.clear_arrangement_review(uuid,uuid,text[])');
BEGIN
    ASSERT v_function IS NOT NULL, 'PRECONDITION: clear RPC not yet implemented; not behavioural Red';
    SELECT id INTO v_original FROM auth.users ORDER BY id LIMIT 1;
    ASSERT v_original IS NOT NULL AND v_original<>v_staff, 'fixture: distinct original/staff identity required';
    INSERT INTO public.event_requests(organiser_id,event_name,status)
    VALUES(v_original,'VERIFY SCRUM64 exact clear','Planning') RETURNING id INTO v_event;
    INSERT INTO public.venues(name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
    VALUES('VERIFY SCRUM64 clear venue','Test wing',100,'{}','{}',
           ARRAY['theatre']::public.room_layout[],ARRAY['AM']::public.booking_slot[]) RETURNING id INTO v_venue;
    INSERT INTO public.venue_booking_requests(venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
    VALUES(v_venue,v_original,v_event,v_today,v_today+1,ARRAY['AM']::public.booking_slot[],
           'approved',v_original,transaction_timestamp()) RETURNING id INTO v_booking;
    INSERT INTO public.equipment(type,total_owned_quantity,home_location,created_by)
    VALUES('VERIFY SCRUM64 clear projector',10,'Test store',v_original) RETURNING id INTO v_equipment;
    INSERT INTO public.equipment_requirements(event_request_id,equipment_type,quantity,recorded_by)
    VALUES(v_event,'VERIFY SCRUM64 clear projector',5,v_original) RETURNING id INTO v_requirement;
    INSERT INTO public.equipment_reservations(equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
    VALUES(v_equipment,v_requirement,v_event,1,v_today-1,v_today+1,v_original) RETURNING id INTO v_reservation;
    INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
    VALUES(v_event,'venue_booking',v_booking,gen_random_uuid(),'event_change',ARRAY['expected_attendance'],
           'Attendance25 to40',transaction_timestamp()-INTERVAL '2 hours') RETURNING id INTO v_t1;
    SELECT to_jsonb(r) INTO v_loaded FROM public.arrangement_reviews r WHERE id=v_t1;
    -- T2 appears after a reviewer loaded T1, before the actual clear action.
    INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
    VALUES(v_event,'venue_booking',v_booking,gen_random_uuid(),'safety_recheck','{}',
           'Later safety recheck',transaction_timestamp()-INTERVAL '1 hour') RETURNING id INTO v_t2;
    INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
    VALUES(v_event,'equipment_reservation',v_reservation,gen_random_uuid(),'equipment_unavailable','{}',
           'Projector unavailable') RETURNING id INTO v_eq;
    INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
    VALUES(v_event,'venue_booking',v_booking,gen_random_uuid(),'event_change',ARRAY['venue_requirements'],
           'Independent rollback target') RETURNING id INTO v_t3;
    SELECT to_jsonb(r) INTO v_newer FROM public.arrangement_reviews r WHERE id=v_t2;
    v_before:=pg_temp.scrum64_clear_state();

    -- AC4-H1 (happy): same-domain staff need not be the historic editor and writes only through server RPC.
    ASSERT has_function_privilege('service_role',v_function,'EXECUTE')
       AND NOT has_function_privilege('anon',v_function,'EXECUTE')
       AND NOT has_function_privilege('authenticated',v_function,'EXECUTE'), 'AC4-H1: RPC grant boundary wrong';
    ASSERT (SELECT prosecdef FROM pg_proc WHERE oid=v_function), 'AC4-H1: clear cannot encapsulate server-only table writes';
    ASSERT EXISTS(SELECT 1 FROM pg_proc p,unnest(p.proconfig)c WHERE p.oid=v_function AND c IN('search_path=','search_path=""')),
        'AC4-H1: clear search_path not empty';
    ASSERT NOT has_table_privilege('service_role','public.arrangement_reviews','INSERT,UPDATE,DELETE,TRUNCATE'),
        'AC4-H1: service acquired direct review mutation privileges';
    v_start:=clock_timestamp();
    SET LOCAL ROLE service_role;
    SELECT * INTO v_row FROM public.clear_arrangement_review(v_t1,v_staff,ARRAY['venue_booking']);
    RESET ROLE;
    v_end:=clock_timestamp();
    ASSERT v_row.cleared_by=v_staff AND v_row.cleared_at BETWEEN v_start AND v_end,
        'AC4-H1: clear audit actor/time is not the current action';
    v_expected:=v_loaded||jsonb_build_object('cleared_at',v_row.cleared_at,'cleared_by',v_staff);
    ASSERT to_jsonb(v_row)=v_expected, 'AC4-H1: clear changed original trigger evidence';
    ASSERT (SELECT to_jsonb(r) FROM public.arrangement_reviews r WHERE id=v_t1)=v_expected,
        'AC4-H1: returned audit differs from stored row';
    v_after:=pg_temp.scrum64_clear_state();
    ASSERT v_after-'reviews'=v_before-'reviews', 'AC4-H1: clear changed resources/event/history/notifications';
    ASSERT (SELECT count(*)=4 FROM public.arrangement_reviews WHERE event_request_id=v_event),
        'AC4-H1: clear added/deleted review evidence';

    -- AC4-X1 (cross-cutting): clearing loaded T1 must retain the newer T2 for the same arrangement.
    ASSERT (SELECT to_jsonb(r) FROM public.arrangement_reviews r WHERE id=v_t2)=v_newer,
        'AC4-X1: stale action changed later review';
    ASSERT (SELECT cleared_at IS NULL FROM public.arrangement_reviews WHERE id=v_t2),
        'AC4-X1: later recheck lost from outstanding truth';
    ASSERT (SELECT count(*)=3 FROM public.arrangement_reviews WHERE event_request_id=v_event AND cleared_at IS NULL),
        'AC4-X1: exact-ID clear did not leave three other reviews outstanding';

    -- AC4-P1 (partition): technical staff can clear only the equipment-domain target with their own identity.
    SELECT to_jsonb(r) INTO v_loaded FROM public.arrangement_reviews r WHERE id=v_eq;
    v_before:=pg_temp.scrum64_clear_state();
    v_start:=clock_timestamp();
    SET LOCAL ROLE service_role;
    SELECT * INTO v_row FROM public.clear_arrangement_review(v_eq,v_tech,ARRAY['equipment_reservation']);
    RESET ROLE;
    v_end:=clock_timestamp();
    ASSERT to_jsonb(v_row)=v_loaded||jsonb_build_object('cleared_at',v_row.cleared_at,'cleared_by',v_tech)
        AND v_row.cleared_at BETWEEN v_start AND v_end, 'AC4-P1: equipment clear audit/original evidence wrong';
    ASSERT (pg_temp.scrum64_clear_state()-'reviews')=(v_before-'reviews'), 'AC4-P1: equipment clear mutated business state';

    v_before:=pg_temp.scrum64_clear_state();
    -- AC4-N1 (negative): the mutation itself refuses a trusted caller lacking this target's domain.
    SET LOCAL ROLE service_role;
    BEGIN
        PERFORM public.clear_arrangement_review(v_t2,v_tech,ARRAY['equipment_reservation']);
        RAISE EXCEPTION 'AC4-N1: wrong-domain clear succeeded';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    RESET ROLE;
    ASSERT pg_temp.scrum64_clear_state()=v_before, 'AC4-N1: forbidden clear mutated state';
    -- AC4-P2 (partition): an empty trusted domain list cannot grant a coordinator staff capability.
    SET LOCAL ROLE service_role;
    BEGIN
        PERFORM public.clear_arrangement_review(v_t2,v_staff,ARRAY[]::text[]);
        RAISE EXCEPTION 'AC4-P2: roleless clear succeeded';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
    RESET ROLE;
    ASSERT pg_temp.scrum64_clear_state()=v_before, 'AC4-P2: roleless clear mutated state';
    -- AC4-N2 (negative): repeat is a specific conflict and never rewrites the first actor/time.
    SET LOCAL ROLE service_role;
    BEGIN
        PERFORM public.clear_arrangement_review(v_t1,v_tech,ARRAY['venue_booking']);
        RAISE EXCEPTION 'AC4-N2: repeated clear succeeded';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
    RESET ROLE;
    ASSERT pg_temp.scrum64_clear_state()=v_before, 'AC4-N2: repeat rewrote audit or other rows';
    -- AC4-N3 (negative): missing identity is distinct from forbidden/repeated and leaves state unchanged.
    SET LOCAL ROLE service_role;
    BEGIN
        PERFORM public.clear_arrangement_review('64000000-0000-4000-8000-000000000099',v_staff,ARRAY['venue_booking']);
        RAISE EXCEPTION 'AC4-N3: missing review clear succeeded';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL; END;
    RESET ROLE;
    ASSERT pg_temp.scrum64_clear_state()=v_before, 'AC4-N3: missing identity mutated state';

    -- AC4-N5 (negative): a real storage failure leaves clear audit and all related data unchanged.
    PERFORM set_config('scrum64.fail_clear_id',v_t3::text,true);
    SET LOCAL ROLE service_role;
    BEGIN
        PERFORM public.clear_arrangement_review(v_t3,v_staff,ARRAY['venue_booking']);
        RAISE EXCEPTION 'AC4-N5: expected injected clear failure';
    EXCEPTION WHEN check_violation THEN
        GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT;
        ASSERT v_message='SCRUM64 injected clear failure', 'AC4-N5: wrong storage failure caught';
    END;
    RESET ROLE;
    ASSERT pg_temp.scrum64_clear_state()=v_before, 'AC4-N5: rejected mutation left partial audit';
    RAISE NOTICE 'SCRUM64 exact-review clear verification PASSED';
END $$;

-- AC4-N4 (negative): browser database roles cannot bypass verified backend identity through the RPC.
SET LOCAL ROLE anon;
DO $$ BEGIN
    BEGIN
        PERFORM public.clear_arrangement_review(gen_random_uuid(),gen_random_uuid(),ARRAY['venue_booking']);
        RAISE EXCEPTION 'AC4-N4: anon executed clear';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
SET LOCAL ROLE authenticated;
DO $$ BEGIN
    BEGIN
        PERFORM public.clear_arrangement_review(gen_random_uuid(),gen_random_uuid(),ARRAY['venue_booking']);
        RAISE EXCEPTION 'AC4-N4: browser authenticated role executed clear';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
ROLLBACK;
