-- Release 1 hotfix 25: an equipment requirement can be marked not essential. Run once,
-- after 0046.
--
-- Q&A #80 and #106: "some events may not require equipment"; "Non-essential follow-up
-- actions may remain outstanding if they do not prevent the event from being ready for
-- confirmation"; and the Event Coordinator, together with the relevant Technical Support
-- Staff, decides whether an incomplete equipment requirement is essential. If it is, the
-- event is not confirmed until it is resolved. Every unreserved requirement blocked the
-- safety review (and so confirmation) with no way to say it did not matter.
--
-- equipment_requirements.essential is true by default, so nothing changes until the
-- assigned Coordinator marks a requirement not essential, with a note recording what was
-- agreed with Technical Support. The readiness check (0046, used by sending for safety
-- review and by the Safety Officer's approval) then leaves that requirement out. Reserving
-- it later still works; marking it essential again puts it back in the check.

ALTER TABLE public.equipment_requirements
    ADD COLUMN IF NOT EXISTS essential boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS essential_note text,
    ADD COLUMN IF NOT EXISTS essential_set_by uuid,
    ADD COLUMN IF NOT EXISTS essential_set_at timestamptz;

ALTER TABLE public.equipment_requirements
    DROP CONSTRAINT IF EXISTS equipment_requirements_essential_note_check,
    ADD CONSTRAINT equipment_requirements_essential_note_check
        CHECK (essential OR (essential_note IS NOT NULL AND btrim(essential_note) <> ''
                             AND char_length(essential_note) <= 2000));

CREATE OR REPLACE FUNCTION public.set_requirement_essential(
    p_requirement_id uuid,
    p_coordinator_id uuid,
    p_essential boolean,
    p_note text
)
RETURNS public.equipment_requirements
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_requirement public.equipment_requirements%ROWTYPE;
    v_status text;
    v_note text := NULLIF(pg_catalog.btrim(p_note), '');
BEGIN
    SELECT * INTO v_requirement FROM public.equipment_requirements
    WHERE id = p_requirement_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'requirement not found' USING ERRCODE = 'P0002';
    END IF;
    IF p_coordinator_id::text IS DISTINCT FROM (
        SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
        WHERE a.event_request_id = v_requirement.event_request_id ORDER BY a.id DESC LIMIT 1
    ) THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    SELECT status INTO v_status FROM public.event_requests
    WHERE id = v_requirement.event_request_id;
    IF v_status IN ('Draft', 'Completed', 'Cancelled', 'Rejected', 'Withdrawn') THEN
        RAISE EXCEPTION 'event is closed' USING ERRCODE = 'P0004';
    END IF;
    IF p_essential IS NULL
       OR (NOT p_essential AND (v_note IS NULL OR pg_catalog.char_length(v_note) > 2000)) THEN
        RAISE EXCEPTION 'a note of 1 to 2000 characters is required to mark a requirement not essential'
            USING ERRCODE = '22023';
    END IF;

    UPDATE public.equipment_requirements
    SET essential = p_essential,
        essential_note = CASE WHEN p_essential THEN NULL ELSE v_note END,
        essential_set_by = p_coordinator_id,
        essential_set_at = pg_catalog.clock_timestamp()
    WHERE id = p_requirement_id
    RETURNING * INTO v_requirement;
    RETURN v_requirement;
END;
$$;

REVOKE ALL ON FUNCTION public.set_requirement_essential(uuid, uuid, boolean, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.set_requirement_essential(uuid, uuid, boolean, text)
    TO service_role;

-- 0046's readiness list, unchanged except that a requirement marked not essential is not
-- an outstanding item.
CREATE OR REPLACE FUNCTION private.event_readiness_issues(p_event_request_id uuid)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO ''
AS $function$
    SELECT
        CASE WHEN EXISTS (
            SELECT 1 FROM public.venue_booking_requests
            WHERE event_request_id = p_event_request_id AND status IN ('approved', 'pending')
        ) THEN '[]'::jsonb
        ELSE jsonb_build_array(jsonb_build_object('kind', 'no_venue_booking'))
        END
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'venue_booking_pending', 'booking_id', b.id, 'venue_name', v.name
            ) ORDER BY b.created_at, b.id)
            FROM public.venue_booking_requests b
            JOIN public.venues v ON v.id = b.venue_id
            WHERE b.event_request_id = p_event_request_id AND b.status = 'pending'
        ), '[]'::jsonb)
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'equipment_not_reserved', 'requirement_id', r.id,
                'equipment_type', r.equipment_type, 'required', r.quantity, 'reserved', r.reserved
            ) ORDER BY r.recorded_at, r.id)
            FROM (
                SELECT q.id, q.equipment_type, q.quantity, q.recorded_at,
                    coalesce((SELECT sum(s.quantity) FROM public.equipment_reservations s
                              WHERE s.requirement_id = q.id), 0)::int AS reserved
                FROM public.equipment_requirements q
                WHERE q.event_request_id = p_event_request_id
                  AND q.essential
            ) r
            WHERE r.reserved < r.quantity
        ), '[]'::jsonb)
        || coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'kind', 'arrangement_needs_review', 'arrangement', 'registration',
                'review_id', r.id, 'reason', r.reason
            ) ORDER BY r.raised_at DESC, r.id DESC)
            FROM public.event_registration_reviews r
            WHERE r.event_request_id = p_event_request_id AND r.cleared_at IS NULL
        ), '[]'::jsonb);
$function$;
