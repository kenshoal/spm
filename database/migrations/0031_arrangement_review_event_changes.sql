-- SCRUM-64: actual significant event edits raise review work in the same transaction.
-- This private audit trigger is the only insert boundary: service_role retains
-- SELECT-only access to reviews and cannot fabricate rows through the Data API.
CREATE OR REPLACE FUNCTION private.record_event_arrangement_reviews()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_common_fields text[] := '{}';
    v_common_reasons text[] := '{}';
    v_venue_fields text[];
    v_venue_reasons text[];
    v_equipment_fields text[];
    v_equipment_reasons text[];
    v_trigger_id uuid;
    v_today date := (pg_catalog.transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
BEGIN
    IF NEW.status IN ('Draft', 'Completed', 'Cancelled', 'Rejected') THEN
        RETURN NEW;
    END IF;

    -- timestamptz equality compares instants, including different UTC offsets.
    -- Preserve array order; no set/reordering semantics are imposed on event dates.
    IF NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times THEN
        v_common_fields := pg_catalog.array_append(v_common_fields, 'proposed_date_times');
        v_common_reasons := pg_catalog.array_append(v_common_reasons, pg_catalog.format(
            'proposed_date_times (Asia/Singapore): %s -> %s',
            ARRAY(SELECT d AT TIME ZONE 'Asia/Singapore' FROM pg_catalog.unnest(OLD.proposed_date_times) AS d),
            ARRAY(SELECT d AT TIME ZONE 'Asia/Singapore' FROM pg_catalog.unnest(NEW.proposed_date_times) AS d)
        ));
    END IF;
    IF NEW.expected_attendance IS DISTINCT FROM OLD.expected_attendance THEN
        v_common_fields := pg_catalog.array_append(v_common_fields, 'expected_attendance');
        v_common_reasons := pg_catalog.array_append(v_common_reasons, pg_catalog.format(
            'expected_attendance: %L -> %L', OLD.expected_attendance, NEW.expected_attendance
        ));
    END IF;
    v_venue_fields := v_common_fields;
    v_venue_reasons := v_common_reasons;
    v_equipment_fields := v_common_fields;
    v_equipment_reasons := v_common_reasons;

    -- Optional blank text is equivalent to absent text, as in the API normaliser.
    IF nullif(pg_catalog.btrim(NEW.venue_requirements), '')
       IS DISTINCT FROM nullif(pg_catalog.btrim(OLD.venue_requirements), '') THEN
        v_venue_fields := pg_catalog.array_append(v_venue_fields, 'venue_requirements');
        v_venue_reasons := pg_catalog.array_append(v_venue_reasons, pg_catalog.format(
            'venue_requirements: %L -> %L', OLD.venue_requirements, NEW.venue_requirements
        ));
    END IF;
    IF nullif(pg_catalog.btrim(NEW.equipment_requirements), '')
       IS DISTINCT FROM nullif(pg_catalog.btrim(OLD.equipment_requirements), '') THEN
        v_equipment_fields := pg_catalog.array_append(v_equipment_fields, 'equipment_requirements');
        v_equipment_reasons := pg_catalog.array_append(v_equipment_reasons, pg_catalog.format(
            'equipment_requirements: %L -> %L', OLD.equipment_requirements, NEW.equipment_requirements
        ));
    END IF;
    IF pg_catalog.cardinality(v_venue_fields) = 0
       AND pg_catalog.cardinality(v_equipment_fields) = 0 THEN
        RETURN NEW;
    END IF;

    -- One recorded direct-update identity spans both domains; it is not a
    -- fabricated change_request_id. Each later update receives a distinct UUID.
    v_trigger_id := pg_catalog.gen_random_uuid();
    IF pg_catalog.cardinality(v_venue_fields) > 0 THEN
        INSERT INTO public.arrangement_reviews
            (event_request_id, arrangement, arrangement_id, trigger_id,
             trigger_type, changed_fields, reason)
        SELECT NEW.id, 'venue_booking', b.id, v_trigger_id, 'event_change',
               v_venue_fields, pg_catalog.array_to_string(v_venue_reasons, '; ')
        FROM public.venue_booking_requests AS b
        WHERE b.event_request_id = NEW.id AND b.status = 'approved'
          AND b.end_date >= v_today;
    END IF;
    IF pg_catalog.cardinality(v_equipment_fields) > 0 THEN
        INSERT INTO public.arrangement_reviews
            (event_request_id, arrangement, arrangement_id, trigger_id,
             trigger_type, changed_fields, reason)
        SELECT NEW.id, 'equipment_reservation', r.id, v_trigger_id, 'event_change',
               v_equipment_fields, pg_catalog.array_to_string(v_equipment_reasons, '; ')
        FROM public.equipment_reservations AS r
        WHERE r.event_request_id = NEW.id AND r.return_date >= v_today;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.record_event_arrangement_reviews()
    FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER record_event_arrangement_reviews
    AFTER UPDATE OF proposed_date_times, expected_attendance,
                    venue_requirements, equipment_requirements
    ON public.event_requests
    FOR EACH ROW EXECUTE FUNCTION private.record_event_arrangement_reviews();
