-- Atomic equipment creation (SCRUM-45).
--
-- POST /equipment previously issued two separate inserts (equipment row,
-- then the first history entry); a failure between them left a row with no
-- audit trail. This function performs both in one transaction and returns
-- the created row, which PostgREST serialises as a JSON object.

CREATE FUNCTION create_equipment(
    p_type varchar,
    p_description text DEFAULT NULL,
    p_total_owned_quantity integer,
    p_home_location varchar,
    p_operational_status varchar DEFAULT 'AVAILABLE',
    p_created_by uuid
)
RETURNS equipment
LANGUAGE plpgsql
AS $$
DECLARE
    v_equipment equipment;
BEGIN
    INSERT INTO equipment (type, description, total_owned_quantity, home_location, operational_status, created_by)
    VALUES (p_type, p_description, p_total_owned_quantity, p_home_location, p_operational_status, p_created_by)
    RETURNING * INTO v_equipment;

    INSERT INTO equipment_status_history (equipment_id, old_status, new_status, reason, changed_by)
    VALUES (v_equipment.id, NULL, v_equipment.operational_status, NULL, p_created_by);

    RETURN v_equipment;
END;
$$;
