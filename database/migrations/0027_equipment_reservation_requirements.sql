-- Equipment reservations against requirements (SCRUM-13). Safe to re-run.
-- Numbered 0027: 0025 landed on dev (SCRUM-48) and 0026 is SCRUM-58's.
-- D7: every reservation names the requirement it fulfils; the event is copied
-- from the requirement by reserve_equipment, never supplied by the caller.
-- Date maths (D-1, transfer day) stays in Python; the RPC trusts
-- p_collection_date / p_return_date, as the other equipment RPCs do.

ALTER TABLE public.equipment_reservations
    ADD COLUMN IF NOT EXISTS requirement_id uuid
        REFERENCES public.equipment_requirements (id);

-- Guard only: the table should already be empty (story decision P2). If not,
-- stop rather than delete someone's rows — any row present before this
-- migration has no requirement_id, so this catches every leftover.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.equipment_reservations WHERE requirement_id IS NULL) THEN
        RAISE EXCEPTION '0027: equipment_reservations has rows with no requirement_id; remove them first';
    END IF;
END $$;

ALTER TABLE public.equipment_reservations ALTER COLUMN requirement_id SET NOT NULL;

-- Outstanding quantity per requirement (D3) and the per-event list (D9).
CREATE INDEX IF NOT EXISTS equipment_reservations_requirement_idx
    ON public.equipment_reservations (requirement_id);
CREATE INDEX IF NOT EXISTS equipment_reservations_event_idx
    ON public.equipment_reservations (event_request_id, created_at, id);

CREATE OR REPLACE FUNCTION public.reserve_equipment(
    p_requirement_id uuid,
    p_equipment_id uuid,
    p_quantity integer,
    p_collection_date date,
    p_return_date date,
    p_created_by uuid
)
RETURNS public.equipment_reservations
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_requirement public.equipment_requirements;
    v_equipment public.equipment;
    v_held integer;
    v_peak integer;
    v_row public.equipment_reservations;
BEGIN
    -- Story decision P1 (D6a): lock the requirement too, so two reservations
    -- against the same requirement from different rows cannot both pass the
    -- D3 check. Lock order: requirement, then equipment. No other function
    -- locks equipment then requirement, so this cannot deadlock.
    SELECT * INTO v_requirement FROM public.equipment_requirements
    WHERE id = p_requirement_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment requirement not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT * INTO v_equipment FROM public.equipment
    WHERE id = p_equipment_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment not found' USING ERRCODE = 'P0002';
    END IF;

    -- AC2 under the lock: only working equipment can be reserved.
    IF v_equipment.operational_status <> 'AVAILABLE' THEN
        RAISE EXCEPTION 'equipment is %', v_equipment.operational_status USING ERRCODE = 'P0004';
    END IF;

    -- D3 under the lock: never over-reserve a requirement.
    SELECT coalesce(sum(quantity), 0) INTO v_held
    FROM public.equipment_reservations WHERE requirement_id = p_requirement_id;
    IF v_held + p_quantity > v_requirement.quantity THEN
        RAISE EXCEPTION 'exceeds requirement' USING ERRCODE = 'P0004';
    END IF;

    -- AC3 under the lock: units held on the row's busiest day in the window.
    SELECT coalesce(max(day_total), 0) INTO v_peak
    FROM (
        SELECT sum(r.quantity) AS day_total
        FROM generate_series(p_collection_date, p_return_date, interval '1 day') AS g(day)
        JOIN public.equipment_reservations r
          ON r.equipment_id = p_equipment_id
         AND r.collection_date <= g.day::date
         AND r.return_date >= g.day::date
        GROUP BY g.day
    ) per_day;
    IF v_peak + p_quantity > v_equipment.total_owned_quantity THEN
        RAISE EXCEPTION 'insufficient units' USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO public.equipment_reservations
        (requirement_id, event_request_id, equipment_id, quantity,
         collection_date, return_date, created_by)
    VALUES
        (p_requirement_id, v_requirement.event_request_id, p_equipment_id, p_quantity,
         p_collection_date, p_return_date, p_created_by)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

-- Same pattern as 0006/0013: server role only.
REVOKE ALL ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    TO service_role;
