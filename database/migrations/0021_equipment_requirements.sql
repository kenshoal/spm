-- Equipment requirements (SCRUM-33): what equipment an event needs, recorded
-- by its assigned Coordinator, with the arrangement status Technical Support
-- works through. Audit fields accompany every non-requested status and move
-- together; the transition table lives in transition_equipment_requirement so
-- it is applied under the row lock (one source of truth, D3/D4). Safe to re-run.

CREATE TABLE IF NOT EXISTS public.equipment_requirements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id),
    equipment_type varchar NOT NULL
        CONSTRAINT equipment_requirements_type_not_blank
            CHECK (btrim(equipment_type) <> ''),
    quantity integer NOT NULL
        CONSTRAINT equipment_requirements_quantity_positive CHECK (quantity >= 1),
    technical_requirements varchar
        CONSTRAINT equipment_requirements_technical_length
            CHECK (technical_requirements IS NULL OR char_length(technical_requirements) <= 2000),
    status varchar NOT NULL DEFAULT 'requested'
        CONSTRAINT equipment_requirements_status_allowed
            CHECK (status IN ('requested', 'in_progress', 'arranged')),
    support_note varchar
        CONSTRAINT equipment_requirements_note_length
            CHECK (support_note IS NULL OR char_length(support_note) <= 2000),
    event_name varchar,
    event_date_times timestamptz[] NOT NULL DEFAULT '{}',
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid,
    updated_at timestamptz,
    -- A requested row has never been touched; any other status records who
    -- and when, and both audit fields move together (AC5-P1..P3, N2, N3).
    CONSTRAINT equipment_requirements_requested_is_untouched
        CHECK (status <> 'requested' OR (updated_by IS NULL AND updated_at IS NULL)),
    CONSTRAINT equipment_requirements_update_complete
        CHECK ((updated_by IS NULL) = (updated_at IS NULL))
);

-- Per-event listing (Coordinator) and the review queue (Technical Support),
-- both oldest first (AC4-X1).
CREATE INDEX IF NOT EXISTS equipment_requirements_event_idx
    ON public.equipment_requirements (event_request_id, recorded_at, id);
CREATE INDEX IF NOT EXISTS equipment_requirements_status_idx
    ON public.equipment_requirements (status, recorded_at, id);

ALTER TABLE public.equipment_requirements ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.equipment_requirements FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.equipment_requirements TO service_role;

CREATE OR REPLACE FUNCTION public.transition_equipment_requirement(
    p_requirement_id uuid,
    p_expected_status varchar,
    p_new_status varchar,
    p_support_note text,
    p_updated_by uuid
)
RETURNS public.equipment_requirements
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_current public.equipment_requirements;
BEGIN
    SELECT * INTO v_current
    FROM public.equipment_requirements
    WHERE id = p_requirement_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment requirement not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_current.status <> p_expected_status THEN
        RAISE EXCEPTION 'stale update: requirement is now %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    -- D3: requested -> in_progress/arranged; in_progress <-> arranged;
    -- in_progress -> in_progress only as a note-only update.
    IF NOT (
        (v_current.status = 'requested'
            AND p_new_status IN ('in_progress', 'arranged'))
        OR (v_current.status = 'in_progress' AND p_new_status = 'arranged')
        OR (v_current.status = 'arranged' AND p_new_status = 'in_progress')
        OR (v_current.status = 'in_progress' AND p_new_status = 'in_progress'
            AND p_support_note IS NOT NULL AND btrim(p_support_note) <> '')
    ) THEN
        RAISE EXCEPTION 'transition not allowed from %', v_current.status
            USING ERRCODE = 'P0004';
    END IF;

    UPDATE public.equipment_requirements
    SET status = p_new_status,
        support_note = COALESCE(p_support_note, support_note),
        updated_by = p_updated_by,
        updated_at = now()
    WHERE id = p_requirement_id
    RETURNING * INTO v_current;

    RETURN v_current;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.transition_equipment_requirement(
    uuid, varchar, varchar, text, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.transition_equipment_requirement(
    uuid, varchar, varchar, text, uuid
) TO service_role;
