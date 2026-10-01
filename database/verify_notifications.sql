-- Run after 0017_notifications.sql.
-- Every mutation is rolled back, so this leaves no notification data behind.

BEGIN;

DO $$
DECLARE
    stored integer;
BEGIN
    -- The same event for the same recipient is stored once, however often it
    -- is retried. This is the insert notificationService sends.
    INSERT INTO public.notifications (recipient_id, event_type, event_id)
    VALUES ('verify-recipient-1', 'verify.event', 'verify-event-1')
    ON CONFLICT (recipient_id, event_id) DO NOTHING;

    INSERT INTO public.notifications (recipient_id, event_type, event_id)
    VALUES ('verify-recipient-1', 'verify.event', 'verify-event-1')
    ON CONFLICT (recipient_id, event_id) DO NOTHING;

    SELECT count(*) INTO stored
    FROM public.notifications
    WHERE event_id = 'verify-event-1';

    IF stored <> 1 THEN
        RAISE EXCEPTION 'A retried event was stored % times instead of once', stored;
    END IF;

    -- The same event may notify a second person.
    INSERT INTO public.notifications (recipient_id, event_type, event_id)
    VALUES ('verify-recipient-2', 'verify.event', 'verify-event-1')
    ON CONFLICT (recipient_id, event_id) DO NOTHING;

    SELECT count(*) INTO stored
    FROM public.notifications
    WHERE event_id = 'verify-event-1';

    IF stored <> 2 THEN
        RAISE EXCEPTION 'A second recipient of one event was not stored';
    END IF;

    -- Without an event_id nothing identifies a retry, so both rows are kept.
    INSERT INTO public.notifications (recipient_id, event_type)
    VALUES ('verify-recipient-3', 'verify.event'),
           ('verify-recipient-3', 'verify.event');

    SELECT count(*) INTO stored
    FROM public.notifications
    WHERE recipient_id = 'verify-recipient-3';

    IF stored <> 2 THEN
        RAISE EXCEPTION 'Events without an event_id were deduplicated';
    END IF;

    -- A non-object payload is refused.
    BEGIN
        INSERT INTO public.notifications (recipient_id, event_type, payload)
        VALUES ('verify-recipient-4', 'verify.event', '[]'::jsonb);
        RAISE EXCEPTION 'A non-object payload was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;

    -- Browser roles have no direct access.
    IF has_table_privilege('anon', 'public.notifications', 'SELECT')
        OR has_table_privilege('authenticated', 'public.notifications', 'SELECT')
    THEN
        RAISE EXCEPTION 'anon or authenticated can read notifications';
    END IF;

    RAISE NOTICE 'ALL NOTIFICATION VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
