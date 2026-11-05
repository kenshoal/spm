-- Hotfix 2 (H1): the owned quantity cannot drop below what is already reserved. Run
-- once, after 0087.
--
-- SCRUM-45 AC2 (Q&A #114): a reduction below the peak quantity already reserved on any
-- day is refused and nothing changes. 0004 left this as a TODO ("validate against
-- reservations once reservations exist"), so Technical Support could cut the stock below
-- units that events had reserved, leaving those reservations short.
--
-- The check runs under the row lock the function already takes, and reserve_equipment
-- takes the same lock, so a reservation racing a cut is serialised with it.
--
-- The peak is the busiest single day across the row's reservations, the same rule as
-- SCRUM-13 AC3. Reservations whose return date is already past are not counted: those
-- units are back on the shelf, and counting them would stop anyone from ever writing off
-- lost equipment after its last event. Released reservations live in
-- equipment_reservation_releases (0072), so they are not in this table.
--
-- Refusal: P0004. Nothing is written, including no history row.
-- 0004 is not edited: the function is replaced here with the same signature.

CREATE OR REPLACE FUNCTION update_equipment_quantity(
    p_equipment_id uuid,
    p_new_quantity integer,
    p_changed_by uuid
)
RETURNS equipment
LANGUAGE plpgsql
AS $$
DECLARE
    v_equipment equipment;
    v_peak integer;
BEGIN
    SELECT * INTO v_equipment
    FROM equipment
    WHERE id = p_equipment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment not found' USING ERRCODE = 'P0002';
    END IF;

    -- The busiest day always falls on some reservation's first day still ahead, so each such
    -- day is tried once and the reservations covering it are added up.
    SELECT coalesce(max(day_total), 0) INTO v_peak
    FROM (
        SELECT (
            SELECT coalesce(sum(r.quantity), 0)
            FROM public.equipment_reservations AS r
            WHERE r.equipment_id = p_equipment_id
              AND r.collection_date <= anchor.day
              AND r.return_date >= anchor.day
        ) AS day_total
        FROM (
            SELECT DISTINCT GREATEST(collection_date, (now() AT TIME ZONE 'Asia/Singapore')::date) AS day
            FROM public.equipment_reservations
            WHERE equipment_id = p_equipment_id
              AND return_date >= (now() AT TIME ZONE 'Asia/Singapore')::date
        ) AS anchor
    ) AS per_day;
    -- A negative total is left to the table's CHECK constraint, as before.
    IF p_new_quantity >= 0 AND p_new_quantity < v_peak THEN
        RAISE EXCEPTION 'below reserved' USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO equipment_quantity_history (equipment_id, old_quantity, new_quantity, changed_by)
    VALUES (p_equipment_id, v_equipment.total_owned_quantity, p_new_quantity, p_changed_by);

    UPDATE equipment
    SET total_owned_quantity = p_new_quantity,
        updated_at = now()
    WHERE id = p_equipment_id
    RETURNING * INTO v_equipment;

    RETURN v_equipment;
END;
$$;
