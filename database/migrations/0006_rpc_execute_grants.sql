-- Fix the RPC EXECUTE grants (supersedes the revokes in 0005).
--
-- 0005 revoked EXECUTE from anon and authenticated, but Postgres grants
-- EXECUTE on new functions to the pseudo-role PUBLIC, and every role
-- (anon, authenticated, service_role) holds it through PUBLIC — so those
-- revokes matched no direct grants and changed nothing. The functions
-- stayed callable by anyone holding the publishable key. (RLS on the
-- tables still blocked the calls inside these SECURITY INVOKER functions,
-- but the intended defence-in-depth was absent.)
--
-- Revoking from PUBLIC removes the grant every role inherits; the service
-- then needs an explicit grant for the service_role key it authenticates
-- with. Assumes the Supabase-provided service_role role.

REVOKE EXECUTE ON FUNCTION transition_equipment_status FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION create_equipment FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION update_equipment_quantity FROM PUBLIC;

GRANT EXECUTE ON FUNCTION transition_equipment_status TO service_role;
GRANT EXECUTE ON FUNCTION create_equipment TO service_role;
GRANT EXECUTE ON FUNCTION update_equipment_quantity TO service_role;
