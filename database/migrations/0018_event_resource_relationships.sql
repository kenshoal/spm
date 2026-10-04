-- Event-to-resource relationships used by Venue Staff and Technical Support.
-- Backend services use the secret key; browsers have no direct table access.

CREATE TABLE IF NOT EXISTS public.venue_booking_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL
        REFERENCES public.event_requests (id) ON DELETE CASCADE,
    venue_id uuid NOT NULL REFERENCES public.venues (id),
    requested_date date NOT NULL,
    slot public.booking_slot NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    notes text CHECK (char_length(notes) <= 2000),
    requested_by uuid NOT NULL REFERENCES auth.users (id),
    reviewed_by uuid REFERENCES auth.users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    CONSTRAINT venue_booking_review_consistent CHECK (
        (status = 'pending' AND reviewed_by IS NULL AND reviewed_at IS NULL)
        OR status = 'cancelled'
        OR (status IN ('approved', 'rejected')
            AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS venue_booking_requests_status_created_idx
    ON public.venue_booking_requests (status, created_at DESC);

CREATE TABLE IF NOT EXISTS public.equipment_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL
        REFERENCES public.event_requests (id) ON DELETE CASCADE,
    equipment_id uuid NOT NULL REFERENCES public.equipment (id),
    quantity integer NOT NULL CHECK (quantity > 0),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reserved', 'rejected', 'cancelled')),
    requirements text CHECK (char_length(requirements) <= 2000),
    requested_by uuid NOT NULL REFERENCES auth.users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS equipment_reservations_status_created_idx
    ON public.equipment_reservations (status, created_at DESC);

ALTER TABLE public.venue_booking_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equipment_reservations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.venue_booking_requests FROM anon, authenticated;
REVOKE ALL ON public.equipment_reservations FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.venue_booking_requests TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.equipment_reservations TO service_role;
