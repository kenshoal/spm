-- SCRUM-35: auditable organiser amendments reviewed by the assigned coordinator.

CREATE TABLE public.event_change_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id) ON DELETE CASCADE,
    organiser_id uuid NOT NULL REFERENCES auth.users (id),
    status text NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'Approved', 'Rejected')),
    explanation text NOT NULL
        CHECK (btrim(explanation) <> '' AND char_length(explanation) <= 2000),
    proposed_changes jsonb NOT NULL
        CHECK (jsonb_typeof(proposed_changes) = 'object' AND proposed_changes <> '{}'::jsonb),
    base_event_updated_at timestamptz NOT NULL,
    coordinator_id varchar(64),
    decision_reason text CHECK (decision_reason IS NULL OR char_length(decision_reason) <= 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);

CREATE UNIQUE INDEX event_change_requests_one_pending_idx
    ON public.event_change_requests (event_request_id)
    WHERE status = 'Pending';

CREATE INDEX event_change_requests_event_created_idx
    ON public.event_change_requests (event_request_id, created_at DESC);

ALTER TABLE public.event_change_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.event_change_requests FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.event_change_requests TO service_role;

CREATE OR REPLACE FUNCTION public.create_event_change_request(
    p_event_request_id uuid,
    p_organiser_id uuid,
    p_explanation text,
    p_proposed_changes jsonb
)
RETURNS public.event_change_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
    v_change public.event_change_requests%ROWTYPE;
    v_allowed_keys constant text[] := ARRAY[
        'proposed_date_times', 'expected_attendance', 'venue_requirements',
        'equipment_requirements', 'registration_needs'
    ];
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id AND organiser_id = p_organiser_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_event.status NOT IN ('Approved', 'Planning') THEN
        RAISE EXCEPTION 'Event request cannot be amended in its current status' USING ERRCODE = 'P0004';
    END IF;
    IF p_proposed_changes IS NULL OR jsonb_typeof(p_proposed_changes) <> 'object'
       OR p_proposed_changes = '{}'::jsonb
       OR EXISTS (
           SELECT 1 FROM jsonb_object_keys(p_proposed_changes) key
           WHERE NOT (key = ANY(v_allowed_keys))
       ) THEN
        RAISE EXCEPTION 'Invalid proposed changes' USING ERRCODE = 'P0004';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM jsonb_each(p_proposed_changes) proposed
        WHERE CASE proposed.key
            WHEN 'proposed_date_times' THEN to_jsonb(v_event.proposed_date_times) IS DISTINCT FROM proposed.value
            WHEN 'expected_attendance' THEN to_jsonb(v_event.expected_attendance) IS DISTINCT FROM proposed.value
            WHEN 'venue_requirements' THEN to_jsonb(v_event.venue_requirements) IS DISTINCT FROM proposed.value
            WHEN 'equipment_requirements' THEN to_jsonb(v_event.equipment_requirements) IS DISTINCT FROM proposed.value
            WHEN 'registration_needs' THEN to_jsonb(v_event.registration_needs) IS DISTINCT FROM proposed.value
            ELSE false
        END
    ) THEN
        RAISE EXCEPTION 'At least one proposed value must differ' USING ERRCODE = 'P0004';
    END IF;

    BEGIN
        INSERT INTO public.event_change_requests (
            event_request_id, organiser_id, explanation, proposed_changes,
            base_event_updated_at
        ) VALUES (
            p_event_request_id, p_organiser_id, btrim(p_explanation),
            p_proposed_changes, v_event.updated_at
        ) RETURNING * INTO v_change;
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'A pending change request already exists' USING ERRCODE = 'P0004';
    END;
    RETURN v_change;
END;
$$;

CREATE OR REPLACE FUNCTION public.decide_event_change_request(
    p_event_request_id uuid,
    p_change_request_id uuid,
    p_coordinator_id varchar,
    p_decision text,
    p_reason text DEFAULT NULL
)
RETURNS public.event_change_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
    v_change public.event_change_requests%ROWTYPE;
    v_assigned_coordinator varchar;
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT coordinator_id INTO v_assigned_coordinator
    FROM public.event_coordinator_assignments
    WHERE event_request_id = p_event_request_id
    ORDER BY assigned_at DESC, id DESC
    LIMIT 1;
    IF v_assigned_coordinator IS DISTINCT FROM p_coordinator_id THEN
        RAISE EXCEPTION 'Caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;

    SELECT * INTO v_change
    FROM public.event_change_requests
    WHERE id = p_change_request_id AND event_request_id = p_event_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found' USING ERRCODE = 'P0002';
    END IF;
    IF v_change.status <> 'Pending' THEN
        RAISE EXCEPTION 'Change request is already decided' USING ERRCODE = 'P0004';
    END IF;
    IF p_decision NOT IN ('Approved', 'Rejected')
       OR (p_decision = 'Rejected' AND coalesce(btrim(p_reason), '') = '') THEN
        RAISE EXCEPTION 'Invalid change decision' USING ERRCODE = 'P0004';
    END IF;

    IF p_decision = 'Approved' AND v_event.updated_at <> v_change.base_event_updated_at THEN
        RAISE EXCEPTION 'Change request is stale' USING ERRCODE = 'P0004';
    END IF;

    IF p_decision = 'Approved' THEN
        UPDATE public.event_requests SET
            proposed_date_times = CASE WHEN v_change.proposed_changes ? 'proposed_date_times'
                THEN ARRAY(SELECT jsonb_array_elements_text(v_change.proposed_changes->'proposed_date_times')::timestamptz)
                ELSE proposed_date_times END,
            expected_attendance = CASE WHEN v_change.proposed_changes ? 'expected_attendance'
                THEN (v_change.proposed_changes->>'expected_attendance')::integer ELSE expected_attendance END,
            venue_requirements = CASE WHEN v_change.proposed_changes ? 'venue_requirements'
                THEN v_change.proposed_changes->>'venue_requirements' ELSE venue_requirements END,
            equipment_requirements = CASE WHEN v_change.proposed_changes ? 'equipment_requirements'
                THEN v_change.proposed_changes->>'equipment_requirements' ELSE equipment_requirements END,
            registration_needs = CASE WHEN v_change.proposed_changes ? 'registration_needs'
                THEN v_change.proposed_changes->>'registration_needs' ELSE registration_needs END
        WHERE id = p_event_request_id;
    END IF;

    UPDATE public.event_change_requests SET
        status = p_decision,
        coordinator_id = p_coordinator_id,
        decision_reason = NULLIF(btrim(p_reason), ''),
        decided_at = now()
    WHERE id = p_change_request_id
    RETURNING * INTO v_change;
    RETURN v_change;
END;
$$;

REVOKE ALL ON FUNCTION public.create_event_change_request(uuid, uuid, text, jsonb)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.decide_event_change_request(uuid, uuid, varchar, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_event_change_request(uuid, uuid, text, jsonb)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.decide_event_change_request(uuid, uuid, varchar, text, text)
    TO service_role;
