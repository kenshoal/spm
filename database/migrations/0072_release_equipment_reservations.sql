-- Release 1 hotfix 11: reservations can be released or replaced. Run once, after 0071.
--
-- Q&A #114 allows equipment to change after it is reserved, and SCRUM-13 and SCRUM-64
-- both left release out. Every reader (availability, reserve_equipment, readiness,
-- review flags) counts rows in equipment_reservations, so a release moves the row
-- into an audit table: all of them stop counting it at once, and who released what
-- and when is kept. A replacement is a release followed by a normal reservation,
-- which runs every availability check again.
--
-- Open reviews of the released reservation are cleared: nothing remains to recheck.
-- A requirement marked arranged goes back to in_progress, because it may no longer
-- be met. Readiness already refuses a short requirement.

CREATE TABLE IF NOT EXISTS public.equipment_reservation_releases (
    reservation_id uuid PRIMARY KEY,
    equipment_id uuid NOT NULL,
    event_request_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    quantity integer NOT NULL,
    collection_date date NOT NULL,
    return_date date NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    released_by uuid,
    released_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 2000)
);

CREATE INDEX IF NOT EXISTS equipment_reservation_releases_event_idx
    ON public.equipment_reservation_releases (event_request_id);

ALTER TABLE public.equipment_reservation_releases ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.equipment_reservation_releases FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.equipment_reservation_releases TO service_role;

CREATE OR REPLACE FUNCTION private.release_reservation(
    p_reservation public.equipment_reservations,
    p_actor uuid,
    p_reason text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.equipment_reservation_releases (
        reservation_id, equipment_id, event_request_id, requirement_id, quantity,
        collection_date, return_date, created_by, created_at, released_by, reason
    ) VALUES (
        p_reservation.id, p_reservation.equipment_id, p_reservation.event_request_id,
        p_reservation.requirement_id, p_reservation.quantity, p_reservation.collection_date,
        p_reservation.return_date, p_reservation.created_by, p_reservation.created_at,
        p_actor, p_reason
    );

    UPDATE public.arrangement_reviews
    SET cleared_at = now(), cleared_by = p_actor
    WHERE arrangement = 'equipment_reservation'
      AND arrangement_id = p_reservation.id
      AND cleared_at IS NULL
      AND p_actor IS NOT NULL;

    DELETE FROM public.equipment_reservations WHERE id = p_reservation.id;
END;
$$;

REVOKE ALL ON FUNCTION private.release_reservation(public.equipment_reservations, uuid, text)
    FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.release_equipment_reservation(
    p_reservation_id uuid,
    p_actor uuid,
    p_reason text
)
RETURNS public.equipment_reservation_releases
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_reservation public.equipment_reservations;
    v_release public.equipment_reservation_releases;
BEGIN
    IF p_actor IS NULL OR nullif(btrim(p_reason), '') IS NULL
       OR char_length(p_reason) > 2000 THEN
        RAISE EXCEPTION 'invalid reservation release' USING ERRCODE = '22023';
    END IF;

    -- The same order as reserve_equipment: requirement first, then the reservation.
    SELECT * INTO v_reservation FROM public.equipment_reservations WHERE id = p_reservation_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reservation not found' USING ERRCODE = 'P0002';
    END IF;
    PERFORM 1 FROM public.equipment_requirements
    WHERE id = v_reservation.requirement_id FOR UPDATE;
    SELECT * INTO v_reservation FROM public.equipment_reservations
    WHERE id = p_reservation_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reservation not found' USING ERRCODE = 'P0002';
    END IF;

    PERFORM private.release_reservation(v_reservation, p_actor, btrim(p_reason));

    UPDATE public.equipment_requirements
    SET status = 'in_progress', updated_by = p_actor, updated_at = now()
    WHERE id = v_reservation.requirement_id AND status = 'arranged';

    SELECT * INTO v_release FROM public.equipment_reservation_releases
    WHERE reservation_id = p_reservation_id;
    RETURN v_release;
END;
$$;

REVOKE ALL ON FUNCTION public.release_equipment_reservation(uuid, uuid, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.release_equipment_reservation(uuid, uuid, text)
    TO service_role;
