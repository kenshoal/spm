-- Release 1 hotfix 24: the assigned Coordinator changes an event's Event Organiser.
-- Run once, after 0080.
--
-- Q&A #59 and #61: delegation is not supported, but "change of event organiser" is
-- (for example when an Organiser's account is deactivated or leaves). Nothing could
-- change event_requests.organiser_id. The customer did not say who does it; the team
-- proposal is the Coordinator assigned to the event, who already manages it.
--
--   * the new Organiser is found by email and must hold the Event Organiser role
--     (same role precedence as 0060 and 0038);
--   * if the event belongs to a client organisation (0019) the new Organiser must be a
--     member of it, so no one outside the client gains access; the event keeps its
--     organisation either way (the stamp trigger already keeps it);
--   * not for a Draft (the Organiser's own), nor Completed, Cancelled, Rejected or
--     Withdrawn events;
--   * a Pending change request moves to the new Organiser, so its outcome reaches them.
-- event_organiser_changes keeps who changed it, from whom, to whom, why and when.

CREATE TABLE IF NOT EXISTS public.event_organiser_changes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id) ON DELETE CASCADE,
    previous_organiser_id uuid NOT NULL,
    new_organiser_id uuid NOT NULL,
    changed_by text NOT NULL,
    reason text NOT NULL CHECK (btrim(reason) <> '' AND char_length(reason) <= 2000),
    changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS event_organiser_changes_event_idx
    ON public.event_organiser_changes (event_request_id, changed_at);

ALTER TABLE public.event_organiser_changes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.event_organiser_changes FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON public.event_organiser_changes TO service_role;

CREATE OR REPLACE FUNCTION public.change_event_organiser(
    p_event_request_id uuid,
    p_coordinator_id text,
    p_new_organiser_email text,
    p_reason text
)
RETURNS public.event_requests
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests%ROWTYPE;
    v_reason text := pg_catalog.btrim(p_reason);
    v_new uuid;
BEGIN
    SELECT * INTO v_event FROM public.event_requests
    WHERE id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;
    IF p_coordinator_id IS DISTINCT FROM (
        SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
        WHERE a.event_request_id = p_event_request_id ORDER BY a.id DESC LIMIT 1
    ) THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    IF v_event.status IN ('Draft', 'Completed', 'Cancelled', 'Rejected', 'Withdrawn') THEN
        RAISE EXCEPTION 'organiser cannot be changed from status %', v_event.status
            USING ERRCODE = 'P0004';
    END IF;
    IF v_reason IS NULL OR v_reason = '' OR pg_catalog.char_length(v_reason) > 2000 THEN
        RAISE EXCEPTION 'a reason of 1 to 2000 characters is required' USING ERRCODE = '22023';
    END IF;

    SELECT u.id INTO v_new FROM auth.users AS u
    WHERE pg_catalog.lower(u.email) = pg_catalog.lower(pg_catalog.btrim(p_new_organiser_email));
    IF v_new IS NULL THEN
        RAISE EXCEPTION 'no event organiser has that email' USING ERRCODE = 'P0006';
    END IF;
    IF v_new = v_event.organiser_id THEN
        RAISE EXCEPTION 'that person already organises this event' USING ERRCODE = '22023';
    END IF;
    -- Effective roles in authService's precedence (as in 0060 and 0038).
    IF NOT EXISTS (
        SELECT 1 FROM auth.users AS u
        WHERE u.id = v_new
          AND 'event_organiser' = ANY (
            CASE
                WHEN EXISTS (SELECT 1 FROM public.staff_roles AS r WHERE r.user_id = u.id)
                    THEN ARRAY(SELECT r.role::text FROM public.staff_roles AS r WHERE r.user_id = u.id)
                WHEN pg_catalog.jsonb_typeof(u.raw_app_meta_data -> 'roles') = 'array'
                    AND pg_catalog.jsonb_array_length(u.raw_app_meta_data -> 'roles') > 0
                    THEN ARRAY(SELECT pg_catalog.jsonb_array_elements_text(u.raw_app_meta_data -> 'roles'))
                WHEN pg_catalog.jsonb_typeof(u.raw_app_meta_data -> 'role') = 'string'
                    AND u.raw_app_meta_data ->> 'role' <> ''
                    THEN ARRAY[u.raw_app_meta_data ->> 'role']
                ELSE ARRAY['attendee']
            END
          )
    ) THEN
        RAISE EXCEPTION 'no event organiser has that email' USING ERRCODE = 'P0006';
    END IF;
    IF v_event.organisation_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.organisation_members AS m
        WHERE m.user_id = v_new AND m.organisation_id = v_event.organisation_id
    ) THEN
        RAISE EXCEPTION 'the new organiser is not in the event''s organisation' USING ERRCODE = 'P0007';
    END IF;

    INSERT INTO public.event_organiser_changes
        (event_request_id, previous_organiser_id, new_organiser_id, changed_by, reason)
    VALUES (p_event_request_id, v_event.organiser_id, v_new, p_coordinator_id, v_reason);

    UPDATE public.event_change_requests SET organiser_id = v_new
    WHERE event_request_id = p_event_request_id AND status = 'Pending';

    UPDATE public.event_requests SET organiser_id = v_new
    WHERE id = p_event_request_id
    RETURNING * INTO v_event;
    RETURN v_event;
END;
$$;

REVOKE ALL ON FUNCTION public.change_event_organiser(uuid, text, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.change_event_organiser(uuid, text, text, text)
    TO service_role;
