-- SCRUM-64 first read slice: persisted review evidence without write workflows.
-- Arrangement IDs remain generic until their future authorised writers validate
-- the owning booking/reservation; this does not depend on SCRUM-13 migration 0027.
CREATE TABLE public.arrangement_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id),
    arrangement text NOT NULL
        CHECK (arrangement IN ('venue_booking', 'equipment_reservation')),
    arrangement_id uuid NOT NULL,
    trigger_id uuid NOT NULL,
    trigger_type text NOT NULL
        CHECK (trigger_type IN ('event_change', 'equipment_unavailable', 'safety_recheck')),
    changed_fields text[] NOT NULL DEFAULT '{}',
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    raised_at timestamptz NOT NULL DEFAULT now(),
    cleared_at timestamptz,
    cleared_by uuid,
    CONSTRAINT arrangement_reviews_clear_audit_pair
        CHECK ((cleared_at IS NULL) = (cleared_by IS NULL)),
    CONSTRAINT arrangement_reviews_trigger_target_unique
        UNIQUE (event_request_id, arrangement, arrangement_id, trigger_type, trigger_id)
);

CREATE INDEX arrangement_reviews_event_time_idx
    ON public.arrangement_reviews (event_request_id, raised_at DESC, id DESC);

ALTER TABLE public.arrangement_reviews ENABLE ROW LEVEL SECURITY;
-- Revoke default grants explicitly, including service-role writes. A later
-- increment must add the validated write boundary before granting write access.
REVOKE ALL ON TABLE public.arrangement_reviews
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.arrangement_reviews TO service_role;
