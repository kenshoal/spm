-- In-app notifications (SCRUM-37).
--
-- One row per person per workflow event. notificationService writes a row for
-- each event it receives on POST /notifications/events and serves them back as
-- the recipient's inbox. Safe to re-run.
--
-- recipient_id is varchar(64), not uuid, matching coordinator_id and
-- assigned_by in event_coordinator_assignments (0011): it holds a user id with
-- no foreign key to auth.users, the same way staff_roles treats user_id (0010).

CREATE TABLE IF NOT EXISTS public.notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id varchar(64) NOT NULL
        CONSTRAINT notifications_recipient_id_not_blank
        CHECK (btrim(recipient_id) <> ''),
    event_type varchar(100) NOT NULL
        CONSTRAINT notifications_event_type_not_blank
        CHECK (btrim(event_type) <> ''),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
        CONSTRAINT notifications_payload_is_object
        CHECK (jsonb_typeof(payload) = 'object'),
    -- The sender's idempotency key, e.g. the outbox event UUID (SCRUM-11).
    event_id varchar(64),
    read_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- A retried event can never notify the same person twice. The service
    -- inserts with ON CONFLICT DO NOTHING against this constraint. Rows with
    -- no event_id never conflict (NULLs are distinct), so every one is kept.
    CONSTRAINT notifications_recipient_event_key UNIQUE (recipient_id, event_id)
);

-- Serves the inbox: one recipient's notifications, newest first.
CREATE INDEX IF NOT EXISTS notifications_recipient_created_idx
    ON public.notifications (recipient_id, created_at DESC, id DESC);

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- No policies: notificationService reaches this table with the secret key,
-- which bypasses RLS. Browsers get no direct access, so a leaked publishable
-- key cannot read anyone's notifications.
REVOKE ALL ON public.notifications FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.notifications TO service_role;
