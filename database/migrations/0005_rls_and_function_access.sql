-- Row-level security + RPC access hardening.
--
-- The backend authenticates with the service-role key, which bypasses RLS,
-- so this migration never affects the service's own reads and writes.
-- Enabling RLS with no policies denies every direct anon/authenticated
-- read and write made with the public (publishable) key; the
-- technical_support role checks stay in the API layer.

ALTER TABLE equipment ENABLE ROW LEVEL SECURITY;
ALTER TABLE equipment_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE equipment_quantity_history ENABLE ROW LEVEL SECURITY;

-- The mutations are exposed only through equipmentService, which verifies
-- the caller and enforces roles; no browser client should call the RPCs
-- directly, and Postgres grants EXECUTE to anon/authenticated by default.
REVOKE EXECUTE ON FUNCTION transition_equipment_status FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION create_equipment FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION update_equipment_quantity FROM anon, authenticated;
