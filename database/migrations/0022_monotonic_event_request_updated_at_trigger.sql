-- Make the event version marker advance even for multiple writes in one transaction.

CREATE OR REPLACE FUNCTION public.set_event_request_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = GREATEST(
        clock_timestamp(),
        OLD.updated_at + interval '1 microsecond'
    );
    RETURN NEW;
END;
$$;
