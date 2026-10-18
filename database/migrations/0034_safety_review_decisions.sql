-- SCRUM-60 increment 2: the Safety Officer's decision. Safe to re-run.
--
-- safety_reviews keeps each decision exactly as made (reason and targets
-- included) and is insert-only. decide_safety_review applies a decision in one
-- transaction: event row FOR UPDATE first, then checks, then the review row,
-- the status-history actor and the status. It takes no row locks on bookings or
-- reservations (SCRUM-58 gate protocol, agreed with Tate and Heng Rui).
--
-- Not here yet (increment 2b, once SCRUM-64 and SCRUM-58's readiness function
-- are on dev): raising arrangement reviews for changes_requested, and refusing
-- approval while reviews or readiness items are outstanding.

CREATE TABLE IF NOT EXISTS public.safety_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id),
    decision text NOT NULL CHECK (decision IN ('approved', 'changes_requested')),
    reason text CHECK (char_length(reason) <= 2000),
    targets jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(targets) = 'array'),
    decided_by uuid NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT safety_review_reason_required CHECK (
        decision = 'approved' OR nullif(btrim(reason), '') IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS safety_reviews_request_idx
    ON public.safety_reviews (event_request_id, decided_at DESC);

ALTER TABLE public.safety_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.safety_reviews FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.safety_reviews TO service_role;

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

    IF p_decision NOT IN ('approved', 'changes_requested')
       OR (p_decision = 'changes_requested' AND nullif(btrim(p_reason), '') IS NULL)
       OR char_length(p_reason) > 2000
       OR p_targets IS NULL OR jsonb_typeof(p_targets) <> 'array' THEN
        RAISE EXCEPTION 'invalid safety decision' USING ERRCODE = '22023';
    END IF;
    FOR v_target IN SELECT value FROM jsonb_array_elements(p_targets) LOOP
        IF jsonb_typeof(v_target) <> 'object'
           OR v_target->>'arrangement' NOT IN ('venue_booking', 'equipment_reservation')
           OR coalesce(v_target->>'id', '') !~*
              '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            RAISE EXCEPTION 'invalid safety decision target' USING ERRCODE = '22023';
        END IF;
    END LOOP;

    INSERT INTO public.safety_reviews (event_request_id, decision, reason, targets, decided_by)
    VALUES (p_event_request_id, p_decision, nullif(btrim(p_reason), ''), p_targets, p_officer_id);

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
