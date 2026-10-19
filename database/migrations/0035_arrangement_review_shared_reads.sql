-- SCRUM-64: one shared outstanding-evidence predicate for server consumers.
-- Return facts and reasons only: no event/resource locks or readiness decision.
CREATE OR REPLACE FUNCTION public.get_outstanding_arrangement_reviews(
    p_event_request_id uuid
)
RETURNS SETOF public.arrangement_reviews
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT review.*
    FROM public.arrangement_reviews AS review
    WHERE review.event_request_id = p_event_request_id
      AND review.cleared_at IS NULL
    ORDER BY review.raised_at DESC, review.id DESC;
$$;
REVOKE ALL ON FUNCTION public.get_outstanding_arrangement_reviews(uuid)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_outstanding_arrangement_reviews(uuid)
    TO service_role;
