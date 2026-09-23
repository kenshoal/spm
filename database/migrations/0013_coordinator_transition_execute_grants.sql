-- Close the direct anon/authenticated EXECUTE grants on the SCRUM-28
-- coordinator transition function (completes 0012).
--
-- Supabase's default privileges grant EXECUTE on every new function in
-- public directly to anon, authenticated and service_role, in addition to
-- the PUBLIC grant Postgres adds. 0012 revoked only PUBLIC, so the direct
-- grants survived and the function stayed callable with the publishable key
-- (found by database/verify_event_request_status_transitions.sql, check 13).
-- As with the equipment RPCs (0005 + 0006), both kinds of grant must go.
--
-- Actual exposure was limited: the function is SECURITY INVOKER and 0007 /
-- 0011 revoke anon and authenticated table access, so such a call failed
-- inside the function. This restores the intended defence in depth.

REVOKE EXECUTE ON FUNCTION advance_event_request_by_coordinator(uuid, varchar, varchar)
    FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION advance_event_request_by_coordinator(uuid, varchar, varchar)
    TO service_role;
