-- Per-type delivery channel for notifications (SCRUM-57).
--
-- notification_channel_settings says how notifications of one event_type are
-- delivered: 'in_app' (inbox only), 'email' (email only) or 'both'. A type with
-- no row is delivered 'in_app', so nothing changes until someone adds a row.
-- Rows are changed in the database; there is no screen or endpoint for it.
--
--   INSERT INTO public.notification_channel_settings (event_type, channel)
--   VALUES ('clarification_requested', 'both')
--   ON CONFLICT (event_type)
--   DO UPDATE SET channel = EXCLUDED.channel, updated_at = now();
--
-- notifications.in_inbox is false for a notification delivered by email only.
-- The row is still stored, because the (recipient_id, event_id) uniqueness is
-- what stops a retried event emailing twice, but the inbox leaves it out.
-- Additive and safe to re-run: existing rows stay visible (default true).

CREATE TABLE IF NOT EXISTS public.notification_channel_settings (
    event_type varchar(100) PRIMARY KEY
        CONSTRAINT notification_channel_settings_event_type_not_blank
        CHECK (btrim(event_type) <> ''),
    channel varchar(10) NOT NULL
        CONSTRAINT notification_channel_settings_channel_allowed
        CHECK (channel IN ('in_app', 'email', 'both')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.notification_channel_settings ENABLE ROW LEVEL SECURITY;

-- No policies, as for public.notifications: only notificationService, with the
-- secret key, reads this table. Browsers get no direct access.
REVOKE ALL ON public.notification_channel_settings FROM anon, authenticated;
GRANT SELECT ON public.notification_channel_settings TO service_role;

ALTER TABLE public.notifications
    ADD COLUMN IF NOT EXISTS in_inbox boolean NOT NULL DEFAULT true;
