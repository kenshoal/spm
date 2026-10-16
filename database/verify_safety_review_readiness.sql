-- SCRUM-58 AC2/AC3a: real Postgres evidence for Planning -> Safety Review; every fixture rolls back.
-- Run after 0030. Requires an existing auth user. Prints ALL SAFETY REVIEW READINESS VERIFICATIONS PASSED.
BEGIN;

-- Fixture helpers live in pg_temp and vanish with the rollback.
CREATE FUNCTION pg_temp.planning_event(p_coordinator varchar) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_event uuid;
BEGIN
    INSERT INTO public.event_requests (organiser_id, event_name, status)
    SELECT id, 'VERIFY SCRUM-58 safety review', 'Draft' FROM auth.users ORDER BY created_at LIMIT 1
    RETURNING id INTO v_event;
    -- No story writes Planning without the earlier steps, so the fixture sets it directly.
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_event;
    INSERT INTO public.event_coordinator_assignments(event_request_id, coordinator_id, assigned_by)
    VALUES (v_event, p_coordinator, 'scrum58-manager');
    RETURN v_event;
END $$;

CREATE FUNCTION pg_temp.booking(p_event uuid, p_venue_name text, p_status public.booking_request_status)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_venue uuid; v_booking uuid;
BEGIN
    INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
        supported_layouts, operating_slots)
    VALUES (p_venue_name, 'Level 1', 100, '{}', '{}', '{theatre}', '{AM,PM}') RETURNING id INTO v_venue;
    INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date,
        end_date, slots, status, decided_by, decided_at, decision_reason)
    VALUES (v_venue, gen_random_uuid(), p_event, DATE '2026-11-02', DATE '2026-11-02', '{AM}', p_status,
        CASE WHEN p_status <> 'pending' THEN gen_random_uuid() END,
        CASE WHEN p_status <> 'pending' THEN now() END,
        CASE WHEN p_status = 'rejected' THEN 'Venue closed' END)
    RETURNING id INTO v_booking;
    RETURN v_booking;
END $$;

-- A requirement for p_required units with reservations of the given sizes against it.
CREATE FUNCTION pg_temp.requirement(p_event uuid, p_type text, p_required int, p_reserved int[])
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_requirement uuid; v_equipment uuid; v_quantity int;
BEGIN
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
    VALUES (p_event, p_type, p_required, gen_random_uuid()) RETURNING id INTO v_requirement;
    INSERT INTO public.equipment (type, total_owned_quantity, home_location)
    VALUES (p_type, 50, 'Store') RETURNING id INTO v_equipment;
    FOREACH v_quantity IN ARRAY p_reserved LOOP
        INSERT INTO public.equipment_reservations (equipment_id, event_request_id, quantity,
            collection_date, return_date, created_by, requirement_id)
        VALUES (v_equipment, p_event, v_quantity, DATE '2026-11-02', DATE '2026-11-02',
            gen_random_uuid(), v_requirement);
    END LOOP;
    RETURN v_requirement;
END $$;

-- Calls the function expecting a refusal; returns the outstanding list for P0005 (else NULL)
-- after asserting the event and its history are untouched.
CREATE FUNCTION pg_temp.refused(p_case text, p_event uuid, p_coordinator varchar, p_errcode text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
    v_before jsonb; v_history bigint; v_state text; v_detail text;
BEGIN
    SELECT to_jsonb(e) INTO v_before FROM public.event_requests e WHERE id = p_event;
    SELECT count(*) INTO v_history FROM public.event_request_status_history WHERE event_request_id = p_event;
    BEGIN
        PERFORM public.send_event_request_for_safety_review(p_event, p_coordinator);
        RAISE EXCEPTION '%: sent for safety review unexpectedly', p_case;
    -- P0004 is also PL/pgSQL's assert_failure, which OTHERS deliberately skips.
    EXCEPTION WHEN SQLSTATE 'P0004' OR OTHERS THEN
        GET STACKED DIAGNOSTICS v_state = RETURNED_SQLSTATE, v_detail = PG_EXCEPTION_DETAIL;
        IF v_state <> p_errcode THEN
            RAISE EXCEPTION '%: expected %, got % (%)', p_case, p_errcode, v_state, SQLERRM;
        END IF;
    END;
    ASSERT (SELECT to_jsonb(e) FROM public.event_requests e WHERE id = p_event) IS NOT DISTINCT FROM v_before,
        p_case || ': refused call changed the event';
    ASSERT (SELECT count(*) = v_history FROM public.event_request_status_history WHERE event_request_id = p_event),
        p_case || ': refused call wrote history';
    RETURN CASE WHEN p_errcode = 'P0005' THEN v_detail::jsonb END;
END $$;

DO $$
DECLARE
    v_event uuid;
    v_booking uuid;
    v_requirement uuid;
    v_history bigint;
    v_outstanding jsonb;
    v_row public.event_request_status_history;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM auth.users) THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;

    -- AC2-H1 (happy): approved booking and every requirement fully reserved (2 + 1 of 3) -> Safety Review,
    -- one history row naming the coordinator.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall A', 'approved');
    PERFORM pg_temp.requirement(v_event, 'Projector', 3, '{2,1}');
    SELECT count(*) INTO v_history FROM public.event_request_status_history WHERE event_request_id = v_event;
    PERFORM public.send_event_request_for_safety_review(v_event, 'scrum58-coordinator');
    ASSERT (SELECT status = 'Safety Review' FROM public.event_requests WHERE id = v_event), 'AC2-H1: not in Safety Review';
    ASSERT (SELECT count(*) = v_history + 1 FROM public.event_request_status_history WHERE event_request_id = v_event),
        'AC2-H1: expected exactly one new history row';
    SELECT * INTO v_row FROM public.event_request_status_history WHERE event_request_id = v_event ORDER BY id DESC LIMIT 1;
    ASSERT v_row.previous_status = 'Planning' AND v_row.new_status = 'Safety Review'
        AND v_row.actor_id = 'scrum58-coordinator' AND v_row.actor_role = 'event_coordinator'
        AND v_row.source = 'coordinator.safety_review', 'AC2-H1: wrong history row';

    -- AC2-P1 (partition): an event that needs no equipment can be sent.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall B', 'approved');
    PERFORM public.send_event_request_for_safety_review(v_event, 'scrum58-coordinator');
    ASSERT (SELECT status = 'Safety Review' FROM public.event_requests WHERE id = v_event), 'AC2-P1: not sent';

    -- AC2-P2 (partition): a rejected booking is ignored when another booking is approved.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall C', 'rejected');
    PERFORM pg_temp.booking(v_event, 'Hall D', 'approved');
    PERFORM public.send_event_request_for_safety_review(v_event, 'scrum58-coordinator');
    ASSERT (SELECT status = 'Safety Review' FROM public.event_requests WHERE id = v_event), 'AC2-P2: not sent';

    -- AC3-N1 (negative): a pending booking blocks, even beside an approved one, and is named.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall E', 'approved');
    v_booking := pg_temp.booking(v_event, 'Hall F', 'pending');
    v_outstanding := pg_temp.refused('AC3-N1', v_event, 'scrum58-coordinator', 'P0005');
    ASSERT v_outstanding = jsonb_build_array(jsonb_build_object(
        'kind', 'venue_booking_pending', 'booking_id', v_booking, 'venue_name', 'Hall F')),
        'AC3-N1: wrong outstanding list ' || v_outstanding::text;

    -- AC3-N2 (negative): no booking at all blocks.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    v_outstanding := pg_temp.refused('AC3-N2', v_event, 'scrum58-coordinator', 'P0005');
    ASSERT v_outstanding = '[{"kind": "no_venue_booking"}]'::jsonb, 'AC3-N2: wrong outstanding list ' || v_outstanding::text;

    -- AC3-N3 (negative): only rejected bookings means no venue, so it blocks.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall G', 'rejected');
    v_outstanding := pg_temp.refused('AC3-N3', v_event, 'scrum58-coordinator', 'P0005');
    ASSERT v_outstanding = '[{"kind": "no_venue_booking"}]'::jsonb, 'AC3-N3: wrong outstanding list ' || v_outstanding::text;

    -- AC3-B1 (boundary): one unit short (2 of 3 reserved) blocks and reports both numbers.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall H', 'approved');
    v_requirement := pg_temp.requirement(v_event, 'Microphone', 3, '{2}');
    v_outstanding := pg_temp.refused('AC3-B1', v_event, 'scrum58-coordinator', 'P0005');
    ASSERT v_outstanding = jsonb_build_array(jsonb_build_object('kind', 'equipment_not_reserved',
        'requirement_id', v_requirement, 'equipment_type', 'Microphone', 'required', 3, 'reserved', 2)),
        'AC3-B1: wrong outstanding list ' || v_outstanding::text;

    -- AC3-B2 (boundary): nothing reserved at all is reported as 0 of 3.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall I', 'approved');
    v_requirement := pg_temp.requirement(v_event, 'Speaker', 3, '{}');
    v_outstanding := pg_temp.refused('AC3-B2', v_event, 'scrum58-coordinator', 'P0005');
    ASSERT v_outstanding->0->>'reserved' = '0' AND v_outstanding->0->>'required' = '3',
        'AC3-B2: wrong outstanding list ' || v_outstanding::text;

    -- AC3-N4 (negative): every outstanding item is listed at once, venue first then equipment.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    v_booking := pg_temp.booking(v_event, 'Hall J', 'pending');
    v_requirement := pg_temp.requirement(v_event, 'Stage light', 4, '{1}');
    v_outstanding := pg_temp.refused('AC3-N4', v_event, 'scrum58-coordinator', 'P0005');
    ASSERT jsonb_array_length(v_outstanding) = 2
        AND v_outstanding->0->>'kind' = 'venue_booking_pending'
        AND v_outstanding->1->>'kind' = 'equipment_not_reserved', 'AC3-N4: wrong outstanding list ' || v_outstanding::text;

    -- AC2-N1 (negative): only Planning can be sent; a ready event in Approved is refused with P0004.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall K', 'approved');
    UPDATE public.event_requests SET status = 'Approved' WHERE id = v_event;
    PERFORM pg_temp.refused('AC2-N1', v_event, 'scrum58-coordinator', 'P0004');

    -- AC2-N2 (negative): sending twice is refused with P0004.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.booking(v_event, 'Hall L', 'approved');
    PERFORM public.send_event_request_for_safety_review(v_event, 'scrum58-coordinator');
    PERFORM pg_temp.refused('AC2-N2', v_event, 'scrum58-coordinator', 'P0004');

    -- AC4-N9 (negative): another coordinator is refused with P0003, before readiness is revealed.
    v_event := pg_temp.planning_event('scrum58-coordinator');
    PERFORM pg_temp.refused('AC4-N9', v_event, 'other-coordinator', 'P0003');

    -- AC4-N10 (negative): a missing event is P0002.
    PERFORM pg_temp.refused('AC4-N10', gen_random_uuid(), 'scrum58-coordinator', 'P0002');

    -- AC4-N11 (negative): browser roles cannot call the function; the server role can.
    ASSERT NOT has_function_privilege('anon',
        'public.send_event_request_for_safety_review(uuid, varchar)', 'EXECUTE'), 'AC4-N11: anon can execute';
    ASSERT NOT has_function_privilege('authenticated',
        'public.send_event_request_for_safety_review(uuid, varchar)', 'EXECUTE'), 'AC4-N11: authenticated can execute';
    ASSERT has_function_privilege('service_role',
        'public.send_event_request_for_safety_review(uuid, varchar)', 'EXECUTE'), 'AC4-N11: service_role cannot execute';

    RAISE NOTICE 'ALL SAFETY REVIEW READINESS VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
