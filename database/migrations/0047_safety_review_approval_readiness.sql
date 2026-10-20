-- SCRUM-60: approval also checks ordinary readiness. Safe to re-run.
--
-- Replaces decide_safety_review from 0045 (not edited). Requires SCRUM-58's
-- 0046 (private.event_readiness_issues) and SCRUM-64's 0035. Only approval
-- changes: before any write it refuses with P0005 when
--   event_readiness_issues(event) || <outstanding arrangement reviews>
-- is non-empty, readiness items first, as in SCRUM-58's handover. Asking for
-- changes, the event FOR UPDATE lock, the 0044 NULL checks, 22023 for invalid
-- targets and the all-or-nothing decision/status/flags/jobs are unchanged.
-- Also refuses the same target listed twice (22023), from the PR #62 review.

CREATE OR REPLACE FUNCTION public.decide_safety_review(
    p_event_request_id uuid,
    p_officer_id uuid,
    p_decision text,
    p_reason text,
    p_targets jsonb
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_current public.event_requests;
    v_target jsonb;
    v_to_status text;
    v_review_id uuid;
    v_outstanding jsonb;
BEGIN
    SELECT * INTO v_current
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    -- The caller's token was checked by eventRequestService; the role is
    -- re-checked here because service_role EXECUTE is not officer authorisation.
    IF NOT EXISTS (
        SELECT 1 FROM public.staff_roles
        WHERE user_id = p_officer_id AND role = 'safety_officer'
    ) THEN
        RAISE EXCEPTION 'caller is not a safety officer' USING ERRCODE = 'P0003';
    END IF;

    IF v_current.status <> 'Safety Review' THEN
        RAISE EXCEPTION 'safety decision not allowed from status %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    -- coalesce: NULL NOT IN (...) is NULL, which IF treats as false.
    IF coalesce(p_decision, '') NOT IN ('approved', 'changes_requested')
       OR (p_decision = 'changes_requested' AND nullif(btrim(p_reason), '') IS NULL)
       OR coalesce(char_length(p_reason), 0) > 2000
       OR p_targets IS NULL OR jsonb_typeof(p_targets) <> 'array' THEN
        RAISE EXCEPTION 'invalid safety decision' USING ERRCODE = '22023';
    END IF;
    -- The same arrangement twice is refused (review of PR #62); ids compare
    -- case-insensitively, as uuids.
    IF (SELECT count(*) FROM jsonb_array_elements(p_targets))
       <> (SELECT count(DISTINCT (value->>'arrangement', lower(value->>'id')))
           FROM jsonb_array_elements(p_targets)) THEN
        RAISE EXCEPTION 'duplicate safety decision target' USING ERRCODE = '22023';
    END IF;
    FOR v_target IN SELECT value FROM jsonb_array_elements(p_targets) LOOP
        IF jsonb_typeof(v_target) <> 'object'
           OR coalesce(v_target->>'arrangement', '') NOT IN ('venue_booking', 'equipment_reservation')
           OR coalesce(v_target->>'id', '') !~*
              '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            RAISE EXCEPTION 'invalid safety decision target' USING ERRCODE = '22023';
        END IF;
    END LOOP;

    -- AC6: approval waits until the event is ready (SCRUM-58's
    -- event_readiness_issues) and every arrangement review is cleared,
    -- cancelled bookings included (SCRUM-64 reader). Both are plain reads with
    -- no child locks. Readiness items come first, then reviews newest first:
    -- the same P0005 list as SCRUM-58's handover.
    IF p_decision = 'approved' THEN
        SELECT private.event_readiness_issues(p_event_request_id)
            || coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                   'kind', 'arrangement_needs_review',
                   'review_id', review.id,
                   'arrangement', review.arrangement,
                   'arrangement_id', review.arrangement_id,
                   'reason', review.reason)
                   ORDER BY review.raised_at DESC, review.id DESC), '[]'::jsonb)
        INTO v_outstanding
        FROM public.get_outstanding_arrangement_reviews(p_event_request_id) AS review;
        IF pg_catalog.jsonb_array_length(v_outstanding) > 0 THEN
            RAISE EXCEPTION 'event has arrangements still marked for review'
                USING ERRCODE = 'P0005', DETAIL = v_outstanding::text;
        END IF;
    END IF;

    INSERT INTO public.safety_reviews (event_request_id, decision, reason, targets, decided_by)
    VALUES (p_event_request_id, p_decision, nullif(btrim(p_reason), ''), p_targets, p_officer_id)
    RETURNING id INTO v_review_id;

    -- AC4c: mark each chosen arrangement for review, linked to this saved
    -- decision and its stored reason. SCRUM-64's helper validates that every
    -- target belongs to this event and enqueues the arrangement notices; any
    -- failure aborts the whole decision. A target outside the event is invalid
    -- input (22023), not a missing event.
    IF p_decision = 'changes_requested' THEN
        BEGIN
            PERFORM private.raise_safety_arrangement_reviews(
                p_event_request_id, v_review_id, p_targets, btrim(p_reason));
        EXCEPTION WHEN SQLSTATE 'P0002' THEN
            RAISE EXCEPTION 'safety decision target is not part of this event'
                USING ERRCODE = '22023';
        END;
    END IF;

    v_to_status := CASE p_decision WHEN 'approved' THEN 'Confirmed' ELSE 'Planning' END;
    PERFORM private.set_event_status_actor(p_event_request_id, p_officer_id::text,
        'safety_officer', 'safety.' || CASE p_decision
            WHEN 'approved' THEN 'approval' ELSE 'changes_requested' END);
    UPDATE public.event_requests
    SET status = v_to_status
    WHERE id = p_event_request_id
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$$;

REVOKE ALL ON FUNCTION public.decide_safety_review(uuid, uuid, text, text, jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.decide_safety_review(uuid, uuid, text, text, jsonb)
    TO service_role;
