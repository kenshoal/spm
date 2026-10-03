-- Atomically record one durable domain event whenever an event request is submitted.
-- Notification delivery is a separate consumer concern and must be idempotent by id.

CREATE TABLE IF NOT EXISTS public.event_request_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL
        REFERENCES public.event_requests (id) ON DELETE CASCADE,
    organiser_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    event_type text NOT NULL
        CHECK (event_type = 'event_request.submitted'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    CONSTRAINT event_request_outbox_one_event_per_request
        UNIQUE (event_request_id, event_type)
);

CREATE INDEX IF NOT EXISTS event_request_outbox_unpublished_idx
    ON public.event_request_outbox (occurred_at)
    WHERE published_at IS NULL;

ALTER TABLE public.event_request_outbox ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.event_request_outbox FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.event_request_outbox TO service_role;

CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION private.enqueue_event_request_submitted()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.event_request_outbox (
        event_request_id,
        organiser_id,
        event_type,
        payload
    )
    VALUES (
        NEW.id,
        NEW.organiser_id,
        'event_request.submitted',
        pg_catalog.jsonb_build_object(
            'event_request_id', NEW.id,
            'organiser_id', NEW.organiser_id,
            'status', NEW.status
        )
    )
    ON CONFLICT (event_request_id, event_type) DO NOTHING;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.enqueue_event_request_submitted()
    FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS enqueue_direct_event_request_submission
    ON public.event_requests;
CREATE TRIGGER enqueue_direct_event_request_submission
    AFTER INSERT ON public.event_requests
    FOR EACH ROW
    WHEN (NEW.status = 'Submitted')
    EXECUTE FUNCTION private.enqueue_event_request_submitted();

DROP TRIGGER IF EXISTS enqueue_draft_event_request_submission
    ON public.event_requests;
CREATE TRIGGER enqueue_draft_event_request_submission
    AFTER UPDATE OF status ON public.event_requests
    FOR EACH ROW
    WHEN (OLD.status = 'Draft' AND NEW.status = 'Submitted')
    EXECUTE FUNCTION private.enqueue_event_request_submitted();
