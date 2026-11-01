-- Release 1 hotfix 8: the assigned Coordinator updates event details. Run once,
-- after 0071.
--
-- SCRUM-29 and Q&A #102: after submission the Organiser asks and the Coordinator
-- updates the record. The only edit path was the Organiser's draft edit. This locks
-- the event, rechecks the assignment and refuses a stale edit through the event's
-- updated_at. The existing trigger (0059) flags arrangements when a significant field
-- changes, so an ordinary edit raises nothing, and 0071 reopens a Confirmed event when
-- it does. Bookings are not moved: a changed date flags them for the Coordinator.

CREATE OR REPLACE FUNCTION public.update_event_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id text,
    p_expected_updated_at timestamptz,
    p_changes jsonb
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_coordinator text;
BEGIN
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC LIMIT 1;
    IF p_coordinator_id IS NULL OR v_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    IF v_event.status NOT IN ('Under Review', 'Approved', 'Planning', 'Confirmed') THEN
        RAISE EXCEPTION 'event details cannot change from status %', v_event.status
            USING ERRCODE = 'P0004';
    END IF;
    IF p_expected_updated_at IS NULL OR v_event.updated_at <> p_expected_updated_at THEN
        RAISE EXCEPTION 'event changed since it was loaded' USING ERRCODE = 'P0004';
    END IF;

    UPDATE public.event_requests SET
        event_name = CASE WHEN p_changes ? 'event_name'
            THEN p_changes->>'event_name' ELSE event_name END,
        purpose = CASE WHEN p_changes ? 'purpose'
            THEN p_changes->>'purpose' ELSE purpose END,
        description = CASE WHEN p_changes ? 'description'
            THEN p_changes->>'description' ELSE description END,
        expected_attendance = CASE WHEN p_changes ? 'expected_attendance'
            THEN (p_changes->>'expected_attendance')::integer ELSE expected_attendance END,
        venue_requirements = CASE WHEN p_changes ? 'venue_requirements'
            THEN p_changes->>'venue_requirements' ELSE venue_requirements END,
        accessibility_needs = CASE WHEN p_changes ? 'accessibility_needs'
            THEN p_changes->>'accessibility_needs' ELSE accessibility_needs END,
        equipment_requirements = CASE WHEN p_changes ? 'equipment_requirements'
            THEN p_changes->>'equipment_requirements' ELSE equipment_requirements END,
        registration_needs = CASE WHEN p_changes ? 'registration_needs'
            THEN p_changes->>'registration_needs' ELSE registration_needs END,
        proposed_date_times = CASE WHEN p_changes ? 'proposed_date_times'
            THEN ARRAY(SELECT value::timestamptz
                       FROM pg_catalog.jsonb_array_elements_text(p_changes->'proposed_date_times'))
            ELSE proposed_date_times END,
        updated_at = GREATEST(pg_catalog.clock_timestamp(), updated_at + interval '1 microsecond')
    WHERE id = p_event_request_id;

    -- Reread: the review trigger may have returned a Confirmed event to Planning (0071)
    -- after the update, and the caller must see the status that was actually saved.
    SELECT * INTO v_event FROM public.event_requests WHERE id = p_event_request_id;
    RETURN v_event;
END;
$$;

REVOKE ALL ON FUNCTION public.update_event_by_coordinator(uuid, text, timestamptz, jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.update_event_by_coordinator(uuid, text, timestamptz, jsonb)
    TO service_role;
