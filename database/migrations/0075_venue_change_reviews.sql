-- Release 1 hotfix 13: venue edits flag the bookings they affect. Run once, after
-- 0074, and only once the readers that accept 'venue_change' are deployed.
--
-- Q&A #120 and #122: a change affecting an existing booking must identify it for
-- review and tell the Coordinator, and must not cancel or rebook it. Only timing
-- changes (0055) and date-range blocks (0064) did. This trigger covers every other
-- path, so nothing can edit a venue and skip it. 0037 queues the review notices.
--
-- Affected: approved, not yet ended bookings at the venue, of live events (0033's
-- rule, as 0064), when
--   * the venue becomes blocked: every such booking;
--   * the maximum capacity falls: bookings whose event expects more people than the
--     new maximum. Events do not record which layout they will use, so a lower
--     capacity for one layout cannot be matched to a booking and is not flagged;
--   * a layout, facility or accessibility feature is removed: every such booking,
--     because an event's venue requirements are free text and cannot be matched.
-- No booking, approval or event status changes.

ALTER TABLE public.arrangement_reviews
    DROP CONSTRAINT arrangement_reviews_trigger_type_check,
    ADD CONSTRAINT arrangement_reviews_trigger_type_check
        CHECK (trigger_type IN (
            'event_change', 'equipment_unavailable', 'safety_recheck',
            'venue_timing_change', 'venue_block', 'venue_change'
        ));

CREATE OR REPLACE FUNCTION private.record_venue_change_reviews()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_today date := (pg_catalog.transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
    v_blocked boolean := NEW.status = 'blocked' AND OLD.status IS DISTINCT FROM 'blocked';
    v_old_capacity integer := OLD.max_capacity;
    v_new_capacity integer := NEW.max_capacity;
    v_removed text[] := '{}';
    v_fields text[] := '{}';
    v_reason text;
BEGIN
    v_removed := ARRAY(
        SELECT value FROM pg_catalog.unnest(OLD.supported_layouts::text[]) AS value
        WHERE value <> ALL (NEW.supported_layouts::text[])
        UNION ALL
        SELECT value FROM pg_catalog.unnest(OLD.facilities) AS value
        WHERE value <> ALL (NEW.facilities)
        UNION ALL
        SELECT value FROM pg_catalog.unnest(OLD.accessibility_features) AS value
        WHERE value <> ALL (NEW.accessibility_features)
    );
    IF v_blocked THEN
        v_fields := v_fields || 'status'::text;
    END IF;
    IF v_new_capacity < v_old_capacity THEN
        v_fields := v_fields || 'capacity'::text;
    END IF;
    IF pg_catalog.cardinality(v_removed) > 0 THEN
        v_fields := v_fields || 'attributes'::text;
    END IF;
    IF pg_catalog.cardinality(v_fields) = 0 THEN
        RETURN NEW;
    END IF;

    v_reason := pg_catalog.format('Venue %s changed: %s. Recheck this booking.', NEW.name,
        pg_catalog.array_to_string(ARRAY[
            CASE WHEN v_blocked THEN 'it is now unavailable' END,
            CASE WHEN v_new_capacity < v_old_capacity
                THEN pg_catalog.format('capacity is now %s', v_new_capacity) END,
            CASE WHEN pg_catalog.cardinality(v_removed) > 0
                THEN pg_catalog.format('it no longer offers %s',
                    pg_catalog.array_to_string(v_removed, ', ')) END
        ], '; '));

    INSERT INTO public.arrangement_reviews
        (event_request_id, arrangement, arrangement_id, trigger_id,
         trigger_type, changed_fields, reason)
    SELECT b.event_request_id, 'venue_booking', b.id, pg_catalog.gen_random_uuid(),
           'venue_change', v_fields, v_reason
    FROM public.venue_booking_requests AS b
    JOIN public.event_requests AS e ON e.id = b.event_request_id
    WHERE b.venue_id = NEW.id
      AND b.status = 'approved'
      AND b.end_date >= v_today
      AND e.status NOT IN ('Draft', 'Completed', 'Cancelled', 'Rejected')
      AND (
          v_blocked
          OR pg_catalog.cardinality(v_removed) > 0
          OR (v_new_capacity < v_old_capacity AND e.expected_attendance > v_new_capacity)
      );

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.record_venue_change_reviews()
    FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS venues_record_change_reviews ON public.venues;
CREATE TRIGGER venues_record_change_reviews
    AFTER UPDATE ON public.venues
    FOR EACH ROW
    EXECUTE FUNCTION private.record_venue_change_reviews();
