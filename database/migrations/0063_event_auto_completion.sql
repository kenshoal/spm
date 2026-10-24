-- SCRUM-40: authoritative final end; never infer or backfill it from arrangements.
ALTER TABLE public.event_requests
    ADD COLUMN final_event_end_at timestamptz,
    ADD CONSTRAINT event_requests_final_end_finite
        CHECK (final_event_end_at IS NULL OR pg_catalog.isfinite(final_event_end_at));

-- The trusted worker supplies one aware sweep instant; history records the real
-- action time through the existing trigger, never the supplied eligibility time.
CREATE OR REPLACE FUNCTION public.complete_overdue_event_request(
    p_event_request_id uuid,
    p_as_of timestamptz
) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
BEGIN
    IF p_event_request_id IS NULL OR p_as_of IS NULL
       OR NOT pg_catalog.isfinite(p_as_of) THEN
        RAISE EXCEPTION 'An event and finite eligibility timestamp are required'
            USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND OR v_event.status <> 'Confirmed'
       OR v_event.final_event_end_at IS NULL THEN
        RETURN FALSE;
    END IF;

    -- Hours mean elapsed time even when the database session crosses DST.
    IF p_as_of <= v_event.final_event_end_at + interval '168 hours' THEN
        RETURN FALSE;
    END IF;

    PERFORM private.set_event_status_actor(
        p_event_request_id, NULL, 'system', 'event_request.auto_completed'
    );
    UPDATE public.event_requests
    SET status = 'Completed'
    WHERE id = p_event_request_id;
    RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION public.complete_overdue_event_request(uuid, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_overdue_event_request(uuid, timestamptz)
    TO service_role;

-- Existing owner-Draft RLS permits ordinary browser writes, not this authoritative
-- field. Keep those policies intact and require the coordinator service boundary.
-- Trusted reschedules invalidate the end; confirmed/terminal ends stay protected.
CREATE OR REPLACE FUNCTION private.protect_event_final_end()
RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
BEGIN
    IF CURRENT_USER IN ('anon', 'authenticated') THEN
        IF TG_OP = 'INSERT' THEN
            IF NEW.final_event_end_at IS NOT NULL THEN
                RAISE EXCEPTION 'Record the final event end through the coordinator workflow'
                    USING ERRCODE = '42501';
            END IF;
        ELSIF NEW.final_event_end_at IS DISTINCT FROM OLD.final_event_end_at THEN
            RAISE EXCEPTION 'Record the final event end through the coordinator workflow'
                USING ERRCODE = '42501';
        END IF;
    END IF;
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF OLD.status IN ('Confirmed', 'Completed', 'Cancelled', 'Rejected') THEN
        IF NEW.final_event_end_at IS DISTINCT FROM OLD.final_event_end_at
           OR (OLD.final_event_end_at IS NOT NULL
               AND NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times) THEN
            RAISE EXCEPTION 'The final event end is fixed after confirmation or closure'
                USING ERRCODE = 'P0004';
        END IF;
    END IF;

    IF NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times THEN
        NEW.final_event_end_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.protect_event_final_end()
    FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER protect_event_final_end
    BEFORE INSERT OR UPDATE OF final_event_end_at, proposed_date_times
    ON public.event_requests
    FOR EACH ROW EXECUTE FUNCTION private.protect_event_final_end();

CREATE OR REPLACE FUNCTION public.set_event_request_final_end(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_final_event_end_at timestamptz
) RETURNS public.event_requests
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_coordinator varchar;
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;
    IF nullif(btrim(p_coordinator_id), '') IS NULL
       OR v_coordinator IS NULL OR v_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'Only the assigned coordinator can record the final end'
            USING ERRCODE = 'P0003';
    END IF;
    IF v_event.status NOT IN ('Approved', 'Planning') THEN
        RAISE EXCEPTION 'Final end can only be recorded while Approved or Planning'
            USING ERRCODE = 'P0004';
    END IF;
    IF p_final_event_end_at IS NULL OR NOT pg_catalog.isfinite(p_final_event_end_at) THEN
        RAISE EXCEPTION 'A finite final event end is required' USING ERRCODE = '22023';
    END IF;

    -- timestamptz equality compares instants, independent of the submitted offset.
    IF v_event.final_event_end_at IS NOT DISTINCT FROM p_final_event_end_at THEN
        RETURN v_event;
    END IF;
    UPDATE public.event_requests
    SET final_event_end_at = p_final_event_end_at
    WHERE id = p_event_request_id
    RETURNING * INTO v_event;
    RETURN v_event;
END;
$$;

REVOKE ALL ON FUNCTION public.set_event_request_final_end(uuid, varchar, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_event_request_final_end(uuid, varchar, timestamptz)
    TO service_role;
