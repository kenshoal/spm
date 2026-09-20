-- Quantity audit trail (SCRUM-45).
--
-- PATCH /equipment/{id}/quantity previously updated the row directly with
-- no audit trail and no concurrency guard. The history table records every
-- change; update_equipment_quantity takes a row lock (FOR UPDATE) so
-- concurrent updates serialise, and raises ERRCODE P0002 for unknown ids.

CREATE TABLE equipment_quantity_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    equipment_id uuid NOT NULL REFERENCES equipment (id) ON DELETE CASCADE,
    old_quantity integer NOT NULL,
    new_quantity integer NOT NULL,
    changed_by uuid NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_eqh_equipment ON equipment_quantity_history (equipment_id, changed_at DESC);

-- TODO: validate p_new_quantity against reservations once reservations exist.
CREATE FUNCTION update_equipment_quantity(
    p_equipment_id uuid,
    p_new_quantity integer,
    p_changed_by uuid
)
RETURNS equipment
LANGUAGE plpgsql
AS $$
DECLARE
    v_equipment equipment;
BEGIN
    SELECT * INTO v_equipment
    FROM equipment
    WHERE id = p_equipment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment not found' USING ERRCODE = 'P0002';
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
