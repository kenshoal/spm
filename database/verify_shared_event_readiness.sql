-- SCRUM-58 AC3b and the shared readiness function (0046): real Postgres evidence; every fixture rolls back.
-- Needs SCRUM-64's arrangement reviews (0030-0040), 0041/0042 (cancelled bookings) and 0046.
-- Prints ALL SHARED EVENT READINESS VERIFICATIONS PASSED.
BEGIN;

CREATE FUNCTION pg_temp.planning_event() RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_event uuid;
BEGIN
    INSERT INTO public.event_requests (organiser_id, event_name, status)
    SELECT id, 'VERIFY SCRUM-58 shared readiness', 'Draft' FROM auth.users ORDER BY created_at LIMIT 1
    RETURNING id INTO v_event;
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_event;
    INSERT INTO public.event_coordinator_assignments(event_request_id, coordinator_id, assigned_by)
    VALUES (v_event, 'scrum58-coordinator', 'scrum58-manager');
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
        end_date, slots, status, decided_by, decided_at, decision_reason, cancelled_by, cancelled_at)
    VALUES (v_venue, gen_random_uuid(), p_event, DATE '2026-11-02', DATE '2026-11-02', '{AM}', p_status,
        CASE WHEN p_status IN ('approved', 'rejected', 'cancelled') THEN gen_random_uuid() END,
        CASE WHEN p_status IN ('approved', 'rejected', 'cancelled') THEN now() END,
        CASE WHEN p_status = 'rejected' THEN 'Venue closed' END,
        CASE WHEN p_status = 'cancelled' THEN gen_random_uuid() END,
        CASE WHEN p_status = 'cancelled' THEN now() END)
    RETURNING id INTO v_booking;
    RETURN v_booking;
END $$;

CREATE FUNCTION pg_temp.requirement(p_event uuid, p_type text, p_required int, p_reserved int)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_requirement uuid; v_equipment uuid;
BEGIN
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
    VALUES (p_event, p_type, p_required, gen_random_uuid()) RETURNING id INTO v_requirement;
    IF p_reserved > 0 THEN
        INSERT INTO public.equipment (type, total_owned_quantity, home_location)
        VALUES (p_type, 50, 'Store') RETURNING id INTO v_equipment;
        INSERT INTO public.equipment_reservations (equipment_id, event_request_id, quantity,
            collection_date, return_date, created_by, requirement_id)
        VALUES (v_equipment, p_event, p_reserved, DATE '2026-11-02', DATE '2026-11-02',
            gen_random_uuid(), v_requirement);
    END IF;
    RETURN v_requirement;
END $$;

-- A SCRUM-64 review flag on one arrangement, raised at a given time.
CREATE FUNCTION pg_temp.flag(p_event uuid, p_arrangement text, p_arrangement_id uuid, p_reason text,
    p_raised_at timestamptz) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v_review uuid;
BEGIN
    INSERT INTO public.arrangement_reviews (event_request_id, arrangement, arrangement_id, trigger_id,
        trigger_type, reason, raised_at)
    VALUES (p_event, p_arrangement, p_arrangement_id, gen_random_uuid(), 'safety_recheck', p_reason, p_raised_at)
    RETURNING id INTO v_review;
    RETURN v_review;
END $$;

-- Calls the handover expecting P0005; returns its outstanding list after asserting nothing changed.
CREATE FUNCTION pg_temp.not_ready(p_case text, p_event uuid) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE v_before jsonb; v_history bigint; v_state text; v_detail text;
BEGIN
    SELECT to_jsonb(e) INTO v_before FROM public.event_requests e WHERE id = p_event;
    SELECT count(*) INTO v_history FROM public.event_request_status_history WHERE event_request_id = p_event;
    BEGIN
        PERFORM public.send_event_request_for_safety_review(p_event, 'scrum58-coordinator');
        RAISE EXCEPTION '%: sent for safety review unexpectedly', p_case;
    -- P0004 is also PL/pgSQL's assert_failure, which OTHERS deliberately skips.
    EXCEPTION WHEN SQLSTATE 'P0004' OR OTHERS THEN
        GET STACKED DIAGNOSTICS v_state = RETURNED_SQLSTATE, v_detail = PG_EXCEPTION_DETAIL;
        IF v_state <> 'P0005' THEN
            RAISE EXCEPTION '%: expected P0005, got % (%)', p_case, v_state, SQLERRM;
        END IF;
    END;
    ASSERT (SELECT to_jsonb(e) FROM public.event_requests e WHERE id = p_event) IS NOT DISTINCT FROM v_before,
        p_case || ': refused call changed the event';
    ASSERT (SELECT count(*) = v_history FROM public.event_request_status_history WHERE event_request_id = p_event),
        p_case || ': refused call wrote history';
    RETURN v_detail::jsonb;
END $$;

DO $$
DECLARE
    v_event uuid;
    v_booking uuid;
    v_cancelled uuid;
    v_requirement uuid;
    v_review uuid;
    v_older uuid;
    v_outstanding jsonb;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM auth.users) THEN RAISE EXCEPTION 'Verification requires an existing auth user'; END IF;

    -- AC3-P1 (partition): the shared function returns exactly the handover's ordinary items, and [] when ready.
    v_event := pg_temp.planning_event();
    v_booking := pg_temp.booking(v_event, 'Hall P', 'pending');
    v_requirement := pg_temp.requirement(v_event, 'Microphone', 3, 2);
    v_outstanding := pg_temp.not_ready('AC3-P1', v_event);
    ASSERT private.event_readiness_issues(v_event) = v_outstanding,
        'AC3-P1: shared function differs from the handover ' || private.event_readiness_issues(v_event)::text;
    ASSERT v_outstanding = jsonb_build_array(
        jsonb_build_object('kind', 'venue_booking_pending', 'booking_id', v_booking, 'venue_name', 'Hall P'),
        jsonb_build_object('kind', 'equipment_not_reserved', 'requirement_id', v_requirement,
            'equipment_type', 'Microphone', 'required', 3, 'reserved', 2)),
        'AC3-P1: wrong ordinary items ' || v_outstanding::text;
    v_event := pg_temp.planning_event();
    PERFORM pg_temp.booking(v_event, 'Hall Q', 'approved');
    ASSERT private.event_readiness_issues(v_event) = '[]'::jsonb, 'AC3-P1: a ready event must give []';

    -- AC2-P12 (partition): a cancelled booking is ignored beside an approved one.
    v_event := pg_temp.planning_event();
    PERFORM pg_temp.booking(v_event, 'Hall R', 'cancelled');
    PERFORM pg_temp.booking(v_event, 'Hall S', 'approved');
    PERFORM public.send_event_request_for_safety_review(v_event, 'scrum58-coordinator');
    ASSERT (SELECT status = 'Safety Review' FROM public.event_requests WHERE id = v_event), 'AC2-P12: not sent';

    -- AC3-N8 (negative): only cancelled bookings means no venue.
    v_event := pg_temp.planning_event();
    PERFORM pg_temp.booking(v_event, 'Hall T', 'cancelled');
    v_outstanding := pg_temp.not_ready('AC3-N8', v_event);
    ASSERT v_outstanding = '[{"kind": "no_venue_booking"}]'::jsonb, 'AC3-N8: wrong list ' || v_outstanding::text;

    -- AC3-N6 (negative): an otherwise ready event with an outstanding review flag is refused,
    -- the flag listed in SCRUM-60's arrangement_needs_review shape.
    v_event := pg_temp.planning_event();
    v_booking := pg_temp.booking(v_event, 'Hall U', 'approved');
    v_review := pg_temp.flag(v_event, 'venue_booking', v_booking, 'Attendance changed', now());
    v_outstanding := pg_temp.not_ready('AC3-N6', v_event);
    ASSERT v_outstanding = jsonb_build_array(jsonb_build_object('kind', 'arrangement_needs_review',
        'review_id', v_review, 'arrangement', 'venue_booking', 'arrangement_id', v_booking,
        'reason', 'Attendance changed')), 'AC3-N6: wrong list ' || v_outstanding::text;

    -- AC3-N7 (negative): a flag on a cancelled booking still blocks until staff clear it.
    v_event := pg_temp.planning_event();
    PERFORM pg_temp.booking(v_event, 'Hall V', 'approved');
    v_cancelled := pg_temp.booking(v_event, 'Hall W', 'cancelled');
    v_review := pg_temp.flag(v_event, 'venue_booking', v_cancelled, 'Date moved', now());
    v_outstanding := pg_temp.not_ready('AC3-N7', v_event);
    ASSERT jsonb_array_length(v_outstanding) = 1 AND v_outstanding->0->>'review_id' = v_review::text,
        'AC3-N7: wrong list ' || v_outstanding::text;

    -- AC3-P2 (partition): once staff clear the flag, the event can be sent.
    PERFORM public.clear_arrangement_review(v_review, gen_random_uuid(), ARRAY['venue_booking']);
    PERFORM public.send_event_request_for_safety_review(v_event, 'scrum58-coordinator');
    ASSERT (SELECT status = 'Safety Review' FROM public.event_requests WHERE id = v_event), 'AC3-P2: not sent after clearing';

    -- AC3-N9 (negative): ordinary items come first, then flags newest first, in one list.
    v_event := pg_temp.planning_event();
    v_booking := pg_temp.booking(v_event, 'Hall X', 'pending');
    v_older := pg_temp.flag(v_event, 'venue_booking', v_booking, 'Older reason', now() - interval '1 hour');
    v_review := pg_temp.flag(v_event, 'venue_booking', gen_random_uuid(), 'Newer reason', now());
    v_outstanding := pg_temp.not_ready('AC3-N9', v_event);
    ASSERT jsonb_array_length(v_outstanding) = 3
        AND v_outstanding->0->>'kind' = 'venue_booking_pending'
        AND v_outstanding->1->>'review_id' = v_review::text
        AND v_outstanding->2->>'review_id' = v_older::text, 'AC3-N9: wrong order ' || v_outstanding::text;

    -- AC4-N19 (negative): browser roles cannot call the shared function; the server role can.
    ASSERT NOT has_function_privilege('anon', 'private.event_readiness_issues(uuid)', 'EXECUTE'), 'AC4-N19: anon';
    ASSERT NOT has_function_privilege('authenticated', 'private.event_readiness_issues(uuid)', 'EXECUTE'), 'AC4-N19: authenticated';
    ASSERT has_function_privilege('service_role', 'private.event_readiness_issues(uuid)', 'EXECUTE'), 'AC4-N19: service_role';
END;
$$;

-- AC4-X1 (cross-cutting): as service_role, the role the API uses, the handover sends a ready event,
-- refuses a flagged one with the flag listed, and the shared function runs.
CREATE TEMP TABLE scrum58_service_role_case (ready uuid, flagged uuid) ON COMMIT DROP;
GRANT SELECT ON scrum58_service_role_case TO service_role;
DO $$
DECLARE v_ready uuid; v_flagged uuid; v_booking uuid;
BEGIN
    v_ready := pg_temp.planning_event();
    PERFORM pg_temp.booking(v_ready, 'Hall Y', 'approved');
    v_flagged := pg_temp.planning_event();
    v_booking := pg_temp.booking(v_flagged, 'Hall Z', 'approved');
    PERFORM pg_temp.flag(v_flagged, 'venue_booking', v_booking, 'Needs a recheck', now());
    INSERT INTO scrum58_service_role_case VALUES (v_ready, v_flagged);
END;
$$;
SET LOCAL ROLE service_role;
DO $$
DECLARE v_ready uuid; v_flagged uuid; v_status text; v_state text; v_detail text;
BEGIN
    SELECT ready, flagged INTO v_ready, v_flagged FROM scrum58_service_role_case;
    ASSERT private.event_readiness_issues(v_ready) = '[]'::jsonb, 'AC4-X1: shared function as service_role';
    SELECT status INTO v_status FROM public.send_event_request_for_safety_review(v_ready, 'scrum58-coordinator');
    ASSERT v_status = 'Safety Review', 'AC4-X1: ready event not sent as service_role';
    BEGIN
        PERFORM public.send_event_request_for_safety_review(v_flagged, 'scrum58-coordinator');
        RAISE EXCEPTION 'AC4-X1: flagged event sent as service_role';
    EXCEPTION WHEN SQLSTATE 'P0004' OR OTHERS THEN
        GET STACKED DIAGNOSTICS v_state = RETURNED_SQLSTATE, v_detail = PG_EXCEPTION_DETAIL;
        ASSERT v_state = 'P0005', 'AC4-X1: expected P0005, got ' || v_state || ' ' || SQLERRM;
        ASSERT v_detail::jsonb->0->>'kind' = 'arrangement_needs_review', 'AC4-X1: flag not listed ' || v_detail;
    END;
    RAISE NOTICE 'ALL SHARED EVENT READINESS VERIFICATIONS PASSED';
END;
$$;
ROLLBACK;
