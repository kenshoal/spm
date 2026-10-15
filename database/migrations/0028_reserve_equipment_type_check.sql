-- Type check inside reserve_equipment (SCRUM-13 D12). Safe to re-run.
-- 0027 is applied to shared development, so it is not edited; this replaces
-- the function body. The only change from 0027 is the D12 block: the
-- catalogue row's type must match the requirement's, checked after both rows
-- are locked and before the status check (the API's order, D10). Everything
-- else is 0027's logic unchanged: lock order requirement -> equipment (D6a),
-- status, outstanding quantity, busiest-day peak, insert with the event
-- copied from the requirement.
-- Known limit: SQL lower() and Python casefold() differ for a few non-ASCII
-- letters (e.g. "ß"); equipment types are ASCII in practice.

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

    -- D12 under the lock: the row's type must match the requirement's, compared
    -- as Python's norm() does: trim, collapse internal whitespace, ignore case.
    -- 22023 (invalid_parameter_value): a bad request, not a lost race.
    IF lower(btrim(regexp_replace(v_equipment.type, '\s+', ' ', 'g')))
       <> lower(btrim(regexp_replace(v_requirement.equipment_type, '\s+', ' ', 'g'))) THEN
        RAISE EXCEPTION 'equipment type % does not match requirement type %',
            v_equipment.type, v_requirement.equipment_type
            USING ERRCODE = '22023';
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

-- CREATE OR REPLACE keeps existing privileges; restated so a fresh
-- environment that runs 0028 alone is also locked down (0006/0013 pattern).
REVOKE ALL ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    TO service_role;
