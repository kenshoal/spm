-- Shared readiness and outstanding reviews in the safety handover (SCRUM-58 AC3b). Safe to re-run.
--
-- private.event_readiness_issues(event) is SCRUM-58's ordinary readiness, moved
-- out of 0039 unchanged so SCRUM-60's approval can call the same rules:
--   * at least one approved venue booking and none pending; rejected and
--     cancelled bookings are ignored;
--   * every equipment requirement's reservations add up to its quantity.
-- It returns the outstanding items as a JSON array, [] when ready, in the order
-- no_venue_booking, venue_booking_pending (oldest first),
-- equipment_not_reserved (oldest first). It takes no row locks: a gate calls it
-- after locking only the event row FOR UPDATE (lock protocol in 0039).
-- SECURITY DEFINER so callers need no grants on venue or equipment tables;
-- EXECUTE for service_role only.
--
-- send_event_request_for_safety_review (0039) is replaced to refuse with P0005
-- on the readiness items followed by every outstanding SCRUM-64 review
-- (get_outstanding_arrangement_reviews, 0035), cancelled bookings included,
-- newest first. Needs 0035 and 0039.

CREATE OR REPLACE FUNCTION private.event_readiness_issues(p_event_request_id uuid)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT
        CASE WHEN EXISTS (
            SELECT 1 FROM public.venue_booking_requests
            WHERE event_request_id = p_event_request_id AND status IN ('approved', 'pending')
        ) THEN '[]'::jsonb
        ELSE jsonb_build_array(jsonb_build_object('kind', 'no_venue_booking'))
        END
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'venue_booking_pending', 'booking_id', b.id, 'venue_name', v.name
            ) ORDER BY b.created_at, b.id)
            FROM public.venue_booking_requests b
            JOIN public.venues v ON v.id = b.venue_id
            WHERE b.event_request_id = p_event_request_id AND b.status = 'pending'
        ), '[]'::jsonb)
        || coalesce((
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
$$;

REVOKE ALL ON FUNCTION private.event_readiness_issues(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.event_readiness_issues(uuid) TO service_role;

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
    v_outstanding jsonb;
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

    -- Ordinary readiness first (shared with SCRUM-60's approval), then every
    -- outstanding SCRUM-64 review newest first, in SCRUM-60's item shape.
    -- Both are plain reads: the event row is the only lock this gate holds.
    v_outstanding := private.event_readiness_issues(p_event_request_id)
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'arrangement_needs_review', 'review_id', review.id,
                'arrangement', review.arrangement, 'arrangement_id', review.arrangement_id,
                'reason', review.reason
            ) ORDER BY review.raised_at DESC, review.id DESC)
            FROM public.get_outstanding_arrangement_reviews(p_event_request_id) AS review
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
