-- Cover the organiser foreign key for deletes and future recipient lookups.
CREATE INDEX IF NOT EXISTS event_request_outbox_organiser_idx
    ON public.event_request_outbox (organiser_id);
