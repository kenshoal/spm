-- Checks migration 0065 (SCRUM-57) by reading the catalog. Writes nothing, so it is
-- safe against the shared database. Raises an exception on the first failure.
--
-- It does NOT try an insert that should be refused: the constraint definition is
-- checked instead. Run the refused insert inside a transaction and roll back
-- (AC2-N1) where a write against the shared database is acceptable.

DO $$
DECLARE
    channel_check text;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO channel_check
    FROM pg_constraint
    WHERE conrelid = 'public.notification_channel_settings'::regclass
      AND conname = 'notification_channel_settings_channel_allowed';
    IF channel_check IS NULL
       OR channel_check NOT LIKE '%in_app%'
       OR channel_check NOT LIKE '%email%'
       OR channel_check NOT LIKE '%both%' THEN
        RAISE EXCEPTION 'channel check missing or wrong: %', channel_check;
    END IF;

    IF NOT (SELECT relrowsecurity FROM pg_class
            WHERE oid = 'public.notification_channel_settings'::regclass) THEN
        RAISE EXCEPTION 'row level security is off on notification_channel_settings';
    END IF;

    IF has_table_privilege('anon', 'public.notification_channel_settings', 'SELECT')
       OR has_table_privilege('authenticated', 'public.notification_channel_settings', 'SELECT') THEN
        RAISE EXCEPTION 'browser roles can read notification_channel_settings';
    END IF;

    IF NOT has_table_privilege('service_role', 'public.notification_channel_settings', 'SELECT') THEN
        RAISE EXCEPTION 'service_role cannot read notification_channel_settings';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'notifications'
          AND column_name = 'in_inbox' AND is_nullable = 'NO'
          AND column_default = 'true'
    ) THEN
        RAISE EXCEPTION 'notifications.in_inbox is missing, nullable or has no default true';
    END IF;

    IF EXISTS (SELECT 1 FROM public.notifications WHERE in_inbox IS NOT TRUE) THEN
        RAISE EXCEPTION 'existing notifications were hidden from the inbox';
    END IF;

    RAISE NOTICE 'notification_channel_settings checks passed';
END $$;
