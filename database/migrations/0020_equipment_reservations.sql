-- Equipment reservations (SCRUM-10). Starts empty; SCRUM-13 writes rows.
-- collection_date = hold start (D-1 plus any transfer day); return_date = event end date.
-- Date maths lives in Python (app/availability.py), not SQL. Safe to re-run.
-- Numbered 0020 (after the SCRUM-39 placeholder table was dropped; see README).

CREATE TABLE IF NOT EXISTS public.equipment_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id uuid NOT NULL REFERENCES public.equipment (id),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id),
    quantity integer NOT NULL
        CONSTRAINT equipment_reservations_quantity_positive CHECK (quantity > 0),
    collection_date date NOT NULL,
    return_date date NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT equipment_reservations_dates_ordered CHECK (return_date >= collection_date)
);

CREATE INDEX IF NOT EXISTS equipment_reservations_equipment_dates_idx
    ON public.equipment_reservations (equipment_id, collection_date, return_date);

ALTER TABLE public.equipment_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.equipment_reservations FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.equipment_reservations TO service_role;
