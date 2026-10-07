-- Covers the auth.users foreign key for organiser deletion and audit lookups.
CREATE INDEX event_change_requests_organiser_idx
    ON public.event_change_requests (organiser_id);
