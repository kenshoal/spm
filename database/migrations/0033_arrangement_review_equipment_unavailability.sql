-- SCRUM-64: correlate reservation review work with the recorded equipment cause.
-- Existing history receives identifiers only; attaching the trigger afterwards
-- does not replay historical transitions or claim reconstructed review work.
ALTER TABLE public.equipment_status_history
    ADD COLUMN review_trigger_id uuid NOT NULL DEFAULT gen_random_uuid(),
    ADD CONSTRAINT equipment_status_history_review_trigger_unique UNIQUE (review_trigger_id);

-- Keep the review table SELECT-only for service_role. This native audit writer
-- is private/non-callable, like the event-detail writer in migration 0030.
CREATE OR REPLACE FUNCTION private.record_equipment_unavailability_reviews()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_today date := (pg_catalog.transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
BEGIN
    IF NEW.old_status IS NULL
       OR NEW.new_status IS NOT DISTINCT FROM NEW.old_status
       OR NEW.new_status NOT IN ('DAMAGED', 'UNDER_REPAIR', 'UNDER_MAINTENANCE', 'RETIRED') THEN
        RETURN NEW;
    END IF;

    INSERT INTO public.arrangement_reviews
        (event_request_id, arrangement, arrangement_id, trigger_id,
         trigger_type, changed_fields, reason)
    SELECT r.event_request_id, 'equipment_reservation', r.id, NEW.review_trigger_id,
           'equipment_unavailable', ARRAY['operational_status'],
           pg_catalog.format('Equipment %s operational_status: %s -> %s; reason: %L',
               NEW.equipment_id, NEW.old_status, NEW.new_status, NEW.reason)
    FROM public.equipment_reservations AS r
    JOIN public.event_requests AS e ON e.id = r.event_request_id
    WHERE r.equipment_id = NEW.equipment_id
      AND r.return_date >= v_today
      AND e.status NOT IN ('Draft', 'Completed', 'Cancelled', 'Rejected');
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.record_equipment_unavailability_reviews()
    FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER record_equipment_unavailability_reviews
    AFTER INSERT ON public.equipment_status_history
    FOR EACH ROW EXECUTE FUNCTION private.record_equipment_unavailability_reviews();
