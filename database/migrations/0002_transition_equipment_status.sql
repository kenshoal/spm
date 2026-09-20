-- Atomic status transition (SCRUM-16).
--
-- The live database has no transition_equipment_status function (verified
-- 2026-09-19), even though the service calls it via RPC. This creates it
-- from the router's RPC contract:
--   transition_equipment_status(p_equipment_id, p_new_status, p_changed_by, p_reason)
-- An unknown equipment_id raises with ERRCODE P0002 so the service can map
-- every not-found RPC failure to 404 without parsing error text.

CREATE FUNCTION transition_equipment_status(
    p_equipment_id uuid,
    p_new_status varchar,
    p_changed_by uuid,
    p_reason varchar DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_old_status varchar(20);
BEGIN
    SELECT operational_status INTO v_old_status
    FROM equipment
    WHERE id = p_equipment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment not found' USING ERRCODE = 'P0002';
    END IF;

    UPDATE equipment
    SET operational_status = p_new_status,
        updated_at = now()
    WHERE id = p_equipment_id;

    INSERT INTO equipment_status_history (equipment_id, old_status, new_status, reason, changed_by)
    VALUES (p_equipment_id, v_old_status, p_new_status, p_reason, p_changed_by);
END;
$$;
