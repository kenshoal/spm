-- SCRUM-64: durable notification work for each newly raised arrangement review.
-- This separate outbox preserves the submission-only outbox's existing contract.
CREATE TABLE public.arrangement_review_notification_outbox (
    review_id uuid PRIMARY KEY REFERENCES public.arrangement_reviews (id),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id),
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
CREATE INDEX arrangement_review_notification_pending_idx
    ON public.arrangement_review_notification_outbox (occurred_at, review_id)
    WHERE published_at IS NULL;
ALTER TABLE public.arrangement_review_notification_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.arrangement_review_notification_outbox
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.arrangement_review_notification_outbox TO service_role;

-- Enqueue the raised snapshot, not a later view of mutable clear/assignment state.
-- Delivery happens after commit; enqueue failure aborts the source transaction.
CREATE OR REPLACE FUNCTION private.enqueue_arrangement_review_notification()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.arrangement_review_notification_outbox
        (review_id, event_request_id, payload)
    VALUES (
        NEW.id,
        NEW.event_request_id,
        (pg_catalog.to_jsonb(NEW) - 'id')
            || pg_catalog.jsonb_build_object('review_id', NEW.id)
    )
    ON CONFLICT (review_id) DO NOTHING;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.enqueue_arrangement_review_notification()
    FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER enqueue_arrangement_review_notification
    AFTER INSERT ON public.arrangement_reviews
    FOR EACH ROW EXECUTE FUNCTION private.enqueue_arrangement_review_notification();
