-- Release 1 hotfix 20: a change request can be partly approved. Run once, after 0071.
--
-- Q&A #104: "A single change request may cover several fields, and some changes may
-- be accepted while others are not. Where a change is not accepted, the relevant
-- reason or follow-up should be communicated to the Event Organiser." A request was
-- approved or rejected whole.
--
-- The Coordinator names the fields to accept and gives a reason for each field not
-- accepted. The request is narrowed to the accepted fields and then goes through the
-- same approval as a whole request (0071), so every existing check, flag and booking
-- plan rule still applies. The refused fields, their proposed values and reasons are
-- kept in rejected_changes, and the request ends as 'Partially Approved'. One
-- transaction: if the approval refuses, nothing is narrowed or recorded.

ALTER TABLE public.event_change_requests
    ADD COLUMN IF NOT EXISTS rejected_changes jsonb;

ALTER TABLE public.event_change_requests
    DROP CONSTRAINT IF EXISTS event_change_requests_status_check,
    ADD CONSTRAINT event_change_requests_status_check
        CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Partially Approved')),
    DROP CONSTRAINT IF EXISTS event_change_requests_rejected_changes_check,
    ADD CONSTRAINT event_change_requests_rejected_changes_check
        CHECK (rejected_changes IS NULL OR jsonb_typeof(rejected_changes) = 'object');

CREATE OR REPLACE FUNCTION public.partially_approve_event_change_request(
    p_event_request_id uuid,
    p_change_request_id uuid,
    p_coordinator_id varchar,
    p_accepted_fields text[],
    p_rejections jsonb,
    p_reason text,
    p_booking_plan jsonb DEFAULT NULL
)
RETURNS public.event_change_requests
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
    v_change public.event_change_requests%ROWTYPE;
    v_coordinator varchar;
    v_keys text[];
    v_accepted text[];
    v_refused text[];
    v_key text;
    v_reason text;
    v_rejected jsonb := '{}'::jsonb;
    v_kept jsonb := '{}'::jsonb;
BEGIN
    -- Event first, as every other decision does, so competing decisions serialise.
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY id DESC LIMIT 1;
    IF p_coordinator_id IS NULL OR pg_catalog.btrim(p_coordinator_id) = ''
       OR v_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    SELECT * INTO v_change FROM public.event_change_requests
    WHERE id = p_change_request_id AND event_request_id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_change.status <> 'Pending' THEN
        RAISE EXCEPTION 'Change request cannot be decided in its current state'
            USING ERRCODE = 'P0004';
    END IF;

    v_keys := ARRAY(SELECT key FROM pg_catalog.jsonb_object_keys(v_change.proposed_changes) AS k(key));
    v_accepted := ARRAY(SELECT DISTINCT a FROM pg_catalog.unnest(p_accepted_fields) AS a);
    IF pg_catalog.cardinality(v_accepted) = 0 THEN
        RAISE EXCEPTION 'Accept at least one field, or reject the request'
            USING ERRCODE = '22023';
    END IF;
    IF NOT (v_accepted <@ v_keys) THEN
        RAISE EXCEPTION 'An accepted field is not part of this request' USING ERRCODE = '22023';
    END IF;
    v_refused := ARRAY(SELECT k FROM pg_catalog.unnest(v_keys) AS k WHERE k <> ALL (v_accepted));
    IF pg_catalog.cardinality(v_refused) = 0 THEN
        RAISE EXCEPTION 'Every field is accepted: approve the request instead'
            USING ERRCODE = '22023';
    END IF;
    IF p_rejections IS NULL OR pg_catalog.jsonb_typeof(p_rejections) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'A reason is required for every field not accepted' USING ERRCODE = '22023';
    END IF;

    FOREACH v_key IN ARRAY v_refused LOOP
        v_reason := CASE WHEN pg_catalog.jsonb_typeof(p_rejections -> v_key) = 'string'
            THEN pg_catalog.btrim(p_rejections ->> v_key) END;
        IF v_reason IS NULL OR v_reason = '' OR pg_catalog.char_length(v_reason) > 2000 THEN
            RAISE EXCEPTION 'A reason of 1 to 2000 characters is required for %', v_key
                USING ERRCODE = '22023';
        END IF;
        v_rejected := v_rejected || pg_catalog.jsonb_build_object(
            v_key, pg_catalog.jsonb_build_object(
                'value', v_change.proposed_changes -> v_key, 'reason', v_reason));
    END LOOP;
    FOREACH v_key IN ARRAY v_accepted LOOP
        v_kept := v_kept || pg_catalog.jsonb_build_object(v_key, v_change.proposed_changes -> v_key);
    END LOOP;

    -- The approval checks the stored proposal, so narrow it first. A refusal inside
    -- the approval raises and undoes this update with everything else.
    UPDATE public.event_change_requests
    SET proposed_changes = v_kept, rejected_changes = v_rejected
    WHERE id = v_change.id;

    IF v_kept ? 'proposed_date_times' THEN
        v_change := public.approve_date_event_change_request(
            p_event_request_id, p_change_request_id, p_coordinator_id, p_reason, p_booking_plan);
    ELSE
        v_change := public.approve_non_date_event_change_request(
            p_event_request_id, p_change_request_id, p_coordinator_id, p_reason);
    END IF;

    UPDATE public.event_change_requests
    SET status = 'Partially Approved'
    WHERE id = v_change.id
    RETURNING * INTO v_change;
    RETURN v_change;
END;
$$;

REVOKE ALL ON FUNCTION public.partially_approve_event_change_request(
    uuid, uuid, varchar, text[], jsonb, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.partially_approve_event_change_request(
    uuid, uuid, varchar, text[], jsonb, text, jsonb) TO service_role;
