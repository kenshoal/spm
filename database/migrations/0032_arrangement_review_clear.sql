-- SCRUM-64: exact-ID clearing preserves the original trigger and later reviews.
-- Only the backend calls this RPC, with actor/domain scope from verified auth.
-- Encapsulate the audit-pair write instead of granting direct table UPDATE.
CREATE OR REPLACE FUNCTION public.clear_arrangement_review(
    p_review_id uuid,
    p_actor_id uuid,
    p_allowed_arrangements text[]
)
RETURNS public.arrangement_reviews
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_review public.arrangement_reviews;
BEGIN
    SELECT * INTO v_review
    FROM public.arrangement_reviews
    WHERE id = p_review_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'arrangement review not found' USING ERRCODE = 'P0002';
    END IF;
    IF p_actor_id IS NULL
       OR NOT coalesce(v_review.arrangement = ANY(p_allowed_arrangements), false) THEN
        RAISE EXCEPTION 'arrangement review domain forbidden' USING ERRCODE = 'P0003';
    END IF;
    IF v_review.cleared_at IS NOT NULL THEN
        RAISE EXCEPTION 'arrangement review already cleared' USING ERRCODE = 'P0004';
    END IF;

    -- The row lock serialises competing clears. No event or resource lock is
    -- needed, and a newer review for the same arrangement is a different row.
    UPDATE public.arrangement_reviews
    SET cleared_at = pg_catalog.clock_timestamp(), cleared_by = p_actor_id
    WHERE id = p_review_id
    RETURNING * INTO v_review;
    RETURN v_review;
END;
$$;
REVOKE ALL ON FUNCTION public.clear_arrangement_review(uuid, uuid, text[])
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.clear_arrangement_review(uuid, uuid, text[])
    TO service_role;
