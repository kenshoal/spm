-- SCRUM-48: one immutable entry in the same transaction as each event status write.
-- CLI scaffold generated in /tmp; numbered here to follow this repository's convention.
CREATE TABLE public.event_request_status_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_request_id uuid NOT NULL REFERENCES public.event_requests(id) ON DELETE CASCADE,
    previous_status varchar(64),
    new_status varchar(64) NOT NULL CHECK (btrim(new_status) <> ''),
    actor_id varchar(64),
    actor_role varchar(64) NOT NULL CHECK (btrim(actor_role) <> ''),
    source varchar(100) NOT NULL CHECK (btrim(source) <> ''),
    entry_kind text NOT NULL CHECK (entry_kind IN ('created', 'transition', 'baseline')),
    occurred_at timestamptz NOT NULL,
    CONSTRAINT event_status_history_actor_required CHECK (actor_role = 'system' OR actor_id IS NOT NULL),
    CONSTRAINT event_status_history_real_transition CHECK (
        (entry_kind = 'transition' AND previous_status IS NOT NULL AND previous_status <> new_status)
        OR (entry_kind IN ('created', 'baseline') AND previous_status IS NULL)
    )
);
CREATE INDEX event_status_history_request_time_idx
    ON public.event_request_status_history(event_request_id, occurred_at, id);
ALTER TABLE public.event_request_status_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.event_request_status_history FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.event_request_status_history TO service_role;

-- A server-only RPC supplies its verified actor immediately before writing status.
-- Context is transaction-local and event-scoped; the trigger consumes it once.
CREATE OR REPLACE FUNCTION private.set_event_status_actor(
    p_event_request_id uuid, p_actor_id text, p_actor_role text, p_source text
) RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
    IF p_event_request_id IS NULL OR nullif(btrim(p_actor_role), '') IS NULL
       OR char_length(p_actor_role) > 64 OR nullif(btrim(p_source), '') IS NULL
       OR char_length(p_source) > 100 OR char_length(p_actor_id) > 64
       OR (p_actor_role <> 'system' AND nullif(btrim(p_actor_id), '') IS NULL) THEN
        RAISE EXCEPTION 'Invalid status history actor context' USING ERRCODE = '22023';
    END IF;
    PERFORM pg_catalog.set_config('app.event_status_actor', pg_catalog.jsonb_build_object(
        'event_request_id', p_event_request_id, 'actor_id', p_actor_id,
        'actor_role', p_actor_role, 'source', p_source
    )::text, true);
END;
$$;
GRANT USAGE ON SCHEMA private TO service_role;
REVOKE ALL ON FUNCTION private.set_event_status_actor(uuid, text, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.set_event_status_actor(uuid, text, text, text) TO service_role;

CREATE OR REPLACE FUNCTION private.record_event_request_status()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_context jsonb := nullif(pg_catalog.current_setting('app.event_status_actor', true), '')::jsonb;
    v_actor text;
    v_role text;
    v_source text;
    v_previous text;
    v_kind text;
    v_time timestamptz;
BEGIN
    PERFORM pg_catalog.set_config('app.event_status_actor', '', true);
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
    IF v_context->>'event_request_id' = NEW.id::text THEN
        v_actor := v_context->>'actor_id';
        v_role := v_context->>'actor_role';
        v_source := v_context->>'source';
    ELSIF TG_OP = 'INSERT' THEN
        v_actor := NEW.organiser_id::text;
        v_role := 'event_organiser';
        v_source := 'event_request.created';
    ELSIF OLD.status = 'Draft' AND NEW.status = 'Submitted' THEN
        v_actor := NEW.organiser_id::text;
        v_role := 'event_organiser';
        v_source := 'event_request.submitted';
    ELSE
        -- A privileged database write without application context is labelled
        -- honestly as system work; never guess a user from current assignment.
        v_actor := NULL;
        v_role := 'system';
        v_source := 'database.status_update';
    END IF;
    v_kind := CASE WHEN TG_OP = 'INSERT' THEN 'created' ELSE 'transition' END;
    IF TG_OP = 'UPDATE' THEN v_previous := OLD.status; END IF;
    SELECT greatest(pg_catalog.clock_timestamp(), max(occurred_at) + interval '1 microsecond')
        INTO v_time FROM public.event_request_status_history WHERE event_request_id = NEW.id;
    INSERT INTO public.event_request_status_history
        (event_request_id, previous_status, new_status, actor_id, actor_role, source, entry_kind, occurred_at)
    VALUES (NEW.id, v_previous, NEW.status, v_actor, v_role, v_source, v_kind, v_time);
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.record_event_request_status() FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER record_event_request_creation AFTER INSERT ON public.event_requests
    FOR EACH ROW EXECUTE FUNCTION private.record_event_request_status();
CREATE TRIGGER record_event_request_status_change AFTER UPDATE OF status ON public.event_requests
    FOR EACH ROW EXECUTE FUNCTION private.record_event_request_status();

-- These are installation-time baselines, not reconstructed creation/transition evidence.
INSERT INTO public.event_request_status_history
    (event_request_id, previous_status, new_status, actor_id, actor_role, source, entry_kind, occurred_at)
SELECT id, NULL, status, NULL, 'system', 'history.recording_started', 'baseline', pg_catalog.clock_timestamp()
FROM public.event_requests;

CREATE OR REPLACE FUNCTION private.protect_event_request_status_history()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    -- Preserve SCRUM-8 discard: cascading removal of an unsubmitted Draft
    -- is the only history deletion permitted. Retained history remains immutable.
    IF TG_OP = 'DELETE' THEN
        IF OLD.new_status = 'Draft'
           AND NOT EXISTS (SELECT 1 FROM public.event_requests WHERE id = OLD.event_request_id)
           AND NOT EXISTS (SELECT 1 FROM public.event_request_status_history
                           WHERE event_request_id = OLD.event_request_id AND new_status <> 'Draft') THEN
            RETURN OLD;
        END IF;
    END IF;
    RAISE EXCEPTION 'Event status history is immutable' USING ERRCODE = 'P0003';
END;
$$;
REVOKE ALL ON FUNCTION private.protect_event_request_status_history() FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER protect_event_status_history BEFORE UPDATE OR DELETE ON public.event_request_status_history
    FOR EACH ROW EXECUTE FUNCTION private.protect_event_request_status_history();
CREATE TRIGGER protect_event_status_history_truncate BEFORE TRUNCATE ON public.event_request_status_history
    FOR EACH STATEMENT EXECUTE FUNCTION private.protect_event_request_status_history();

-- Pin the SCRUM-28 transition function's name-resolution path. The original
-- function used an unqualified composite type, so CREATE OR REPLACE is needed
-- to qualify that type before an empty search path can be used safely.
CREATE OR REPLACE FUNCTION public.advance_event_request_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_to_status varchar
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_current public.event_requests;
    v_latest_coordinator varchar;
BEGIN
    SELECT * INTO v_current
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_latest_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;

    IF v_latest_coordinator IS NULL OR v_latest_coordinator <> p_coordinator_id THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    IF NOT (
        (p_to_status = 'Under Review' AND v_current.status = 'Submitted')
        OR (p_to_status = 'Completed' AND v_current.status = 'Confirmed')
        OR (
            p_to_status = 'Cancelled'
            AND v_current.status IN (
                'Submitted', 'Under Review', 'Changes Requested',
                'Approved', 'Planning', 'Confirmed'
            )
        )
    ) THEN
        RAISE EXCEPTION 'transition not allowed from status %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.' || CASE p_to_status
            WHEN 'Under Review' THEN 'review' WHEN 'Completed' THEN 'completion' ELSE 'cancellation' END);
    UPDATE public.event_requests
    SET status = p_to_status
    WHERE id = p_event_request_id
      AND status = v_current.status
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.advance_event_request_by_coordinator(
    uuid, varchar, varchar
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.advance_event_request_by_coordinator(
    uuid, varchar, varchar
) TO service_role;

CREATE OR REPLACE FUNCTION public.decide_event_request_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_decision_status varchar,
    p_reason text DEFAULT NULL
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_current public.event_requests%ROWTYPE;
    v_assigned_coordinator varchar;
BEGIN
    SELECT * INTO v_current
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_assigned_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;

    IF v_assigned_coordinator IS NULL
       OR v_assigned_coordinator <> p_coordinator_id THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator'
            USING ERRCODE = 'P0003';
    END IF;

    IF v_current.status <> 'Under Review'
       OR p_decision_status NOT IN (
           'Changes Requested', 'Approved', 'Rejected'
       ) THEN
        RAISE EXCEPTION 'review decision not allowed from status %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    IF p_decision_status IN ('Changes Requested', 'Rejected')
       AND nullif(btrim(p_reason), '') IS NULL THEN
        RAISE EXCEPTION 'reason required for review decision'
            USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO public.event_request_review_decisions (
        event_request_id, coordinator_id, decision_status, reason
    ) VALUES (
        p_event_request_id,
        p_coordinator_id,
        p_decision_status,
        nullif(btrim(p_reason), '')
    );

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.decision');
    UPDATE public.event_requests
    SET status = p_decision_status
    WHERE id = p_event_request_id
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$$;

REVOKE ALL ON FUNCTION public.decide_event_request_by_coordinator(
    uuid, varchar, varchar, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.decide_event_request_by_coordinator(
    uuid, varchar, varchar, text
) TO service_role;


CREATE OR REPLACE FUNCTION public.resume_event_request_review_by_coordinator(
    p_event_request_id uuid,
    p_coordinator_id varchar
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_request public.event_requests%ROWTYPE;
    v_decision public.event_request_review_decisions%ROWTYPE;
    v_assigned_coordinator varchar;
BEGIN
    SELECT * INTO v_request
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_assigned_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC
    LIMIT 1;

    IF v_assigned_coordinator IS NULL
       OR v_assigned_coordinator <> p_coordinator_id THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator'
            USING ERRCODE = 'P0003';
    END IF;

    SELECT * INTO v_decision
    FROM public.event_request_review_decisions
    WHERE event_request_id = p_event_request_id
      AND decision_status = 'Changes Requested'
    ORDER BY id DESC
    LIMIT 1;

    IF v_request.status <> 'Changes Requested'
       OR v_decision.organiser_response IS NULL THEN
        RAISE EXCEPTION 'review cannot resume before organiser response'
            USING ERRCODE = 'P0004';
    END IF;

    PERFORM private.set_event_status_actor(p_event_request_id, p_coordinator_id,
        'event_coordinator', 'coordinator.resume_review');
    UPDATE public.event_requests
    SET status = 'Under Review'
    WHERE id = p_event_request_id AND status = 'Changes Requested'
    RETURNING * INTO v_request;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'review status changed concurrently'
            USING ERRCODE = 'P0004';
    END IF;

    RETURN v_request;
END;
$$;

REVOKE ALL ON FUNCTION public.resume_event_request_review_by_coordinator(
    uuid, varchar
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.resume_event_request_review_by_coordinator(
    uuid, varchar
) TO service_role;
