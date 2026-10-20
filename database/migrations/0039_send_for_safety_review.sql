-- Planning -> Safety Review (SCRUM-58 AC2, AC3a). Safe to re-run.
--
-- A separate function rather than another branch in
-- advance_event_request_by_coordinator: only this move has readiness rules, and
-- keeping them here leaves the shared function (0025, 0026, 0029) untouched.
--
-- Ready means (approved by the story owner, 13-16 Oct 2026):
--   * at least one approved venue booking and none still pending; rejected
--     bookings are ignored, since a booking cannot be withdrawn and one refusal
--     must not block the event forever;
--   * every equipment requirement fully covered by its reservations (SCRUM-13),
--     not by the manual 'arranged' status. No requirements is ready.
-- Items marked for review (SCRUM-64, AC3b) are not checked yet.
--
-- Not ready raises P0005 with the outstanding items as a JSON array in DETAIL,
-- so the API can say what is missing without a second, racy read.
--
-- Lock protocol (agreed with SCRUM-64/60, 16 Oct 2026): a gate locks ONLY the
-- event row, FOR UPDATE, and reads everything else unlocked, so it never waits
-- on anything while holding the event. Writers that can make an event unready
-- lock their own rows first and reach the event last, through the FK KEY SHARE
-- taken when they insert a row referencing it; that conflicts with FOR UPDATE,
-- so they either commit before the gate reads or wait until it commits. Locking
-- requirements here as well deadlocked against reserve_equipment (requirement
-- -> equipment -> event), shown by test_safety_review_concurrency.py.
-- Known gap: venue_booking_requests.event_request_id has no FK, so a booking
-- created mid-handover is not serialised by this.

CREATE OR REPLACE FUNCTION public.send_event_request_for_safety_review(
    p_event_request_id uuid,
    p_coordinator_id varchar
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_current public.event_requests;
    v_latest_coordinator varchar;
    v_outstanding jsonb := '[]'::jsonb;
BEGIN
    SELECT * INTO v_current
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_latest_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;

    -- Assignment before readiness, so nobody else learns what an event is missing.
    IF v_latest_coordinator IS NULL OR v_latest_coordinator <> p_coordinator_id THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    IF v_current.status <> 'Planning' THEN
        RAISE EXCEPTION 'transition not allowed from status %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.venue_booking_requests
        WHERE event_request_id = p_event_request_id AND status IN ('approved', 'pending')
    ) THEN
        v_outstanding := v_outstanding || jsonb_build_array(jsonb_build_object('kind', 'no_venue_booking'));
    END IF;

    v_outstanding := v_outstanding || coalesce((
        SELECT jsonb_agg(jsonb_build_object(
            'kind', 'venue_booking_pending', 'booking_id', b.id, 'venue_name', v.name
        ) ORDER BY b.created_at, b.id)
        FROM public.venue_booking_requests b
        JOIN public.venues v ON v.id = b.venue_id
        WHERE b.event_request_id = p_event_request_id AND b.status = 'pending'
    ), '[]'::jsonb);

    v_outstanding := v_outstanding || coalesce((
        SELECT jsonb_agg(jsonb_build_object(
            'kind', 'equipment_not_reserved', 'requirement_id', r.id,
            'equipment_type', r.equipment_type, 'required', r.quantity, 'reserved', r.reserved
        ) ORDER BY r.recorded_at, r.id)
        FROM (
            SELECT q.id, q.equipment_type, q.quantity, q.recorded_at,
                coalesce((SELECT sum(s.quantity) FROM public.equipment_reservations s
                          WHERE s.requirement_id = q.id), 0)::int AS reserved
            FROM public.equipment_requirements q
            WHERE q.event_request_id = p_event_request_id
        ) r
        WHERE r.reserved < r.quantity
    ), '[]'::jsonb);

    IF jsonb_array_length(v_outstanding) > 0 THEN
        RAISE EXCEPTION 'event request is not ready for safety review'
            USING ERRCODE = 'P0005', DETAIL = v_outstanding::text;
    END IF;

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.safety_review');
    UPDATE public.event_requests
    SET status = 'Safety Review'
    WHERE id = p_event_request_id
      AND status = v_current.status
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.send_event_request_for_safety_review(uuid, varchar)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.send_event_request_for_safety_review(uuid, varchar)
    TO service_role;
