-- Release 1 hotfix 10: a cancelled event stops holding venues and equipment.
-- Run once, after 0072.
--
-- The Week 1 brief and Q&A #60 say a cancelled event must not stay committed. Until
-- now cancelling only changed the status, so approved bookings kept blocking the
-- venue and reservations kept counting. Tentative holds already stop at once (0066).
--
-- This runs in the cancelling transaction, so a failure leaves the event uncancelled.
-- Bookings keep their decision fields and are recorded as cancelled by the event's
-- Coordinator; releases are recorded in equipment_reservation_releases. Requirements
-- are left as they are: they describe what the cancelled event needed.

CREATE OR REPLACE FUNCTION private.release_arrangements_on_event_cancel()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_actor uuid;
    v_reservation public.equipment_reservations;
BEGIN
    -- coordinator_id is text; only a real uuid can be recorded as who cancelled.
    SELECT CASE WHEN coordinator_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                THEN coordinator_id::uuid END INTO v_actor
    FROM public.event_coordinator_assignments
    WHERE event_request_id = NEW.id
    ORDER BY id DESC LIMIT 1;

    UPDATE public.venue_booking_requests
    -- A booking must record who cancelled it; the coordinator is a uuid in every real
    -- event, and the requester stands in only where the stored id is not one.
    SET status = 'cancelled', cancelled_by = COALESCE(v_actor, requested_by), cancelled_at = now()
    WHERE event_request_id = NEW.id AND status IN ('pending', 'approved');

    FOR v_reservation IN
        SELECT * FROM public.equipment_reservations
        WHERE event_request_id = NEW.id
        ORDER BY id
        FOR UPDATE
    LOOP
        PERFORM private.release_reservation(v_reservation, v_actor, 'Event cancelled');
    END LOOP;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.release_arrangements_on_event_cancel()
    FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS event_requests_release_arrangements_on_cancel ON public.event_requests;
CREATE TRIGGER event_requests_release_arrangements_on_cancel
    AFTER UPDATE OF status ON public.event_requests
    FOR EACH ROW
    WHEN (NEW.status = 'Cancelled' AND OLD.status IS DISTINCT FROM 'Cancelled')
    EXECUTE FUNCTION private.release_arrangements_on_event_cancel();
