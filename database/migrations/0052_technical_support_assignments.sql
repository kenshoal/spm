-- Technical support requirements, staff skills and assignments (SCRUM-19). Safe to re-run.
--
-- The assigned Coordinator records what technical support an event needs (a
-- description plus one skill tag), sees a candidate list of Technical Support
-- Staff who hold that skill, and assigns them. "Suitable" means the person
-- holds the technical_support role AND the requirement's skill tag; no
-- availability or double-booking check exists in this slice (Jira SCRUM-19,
-- customer clarification #6).
--
-- Errcode contract (the service maps on these, never on message text):
--   P0002 event request not found / technical support requirement not found
--   P0003 caller is not the latest-assigned coordinator
--   P0004 technical support not allowed from the current status
--   P0005 staff member is not suitable
--   23505 duplicate assignment (unique constraint, one row per requirement and
--         staff member)
--
-- The two write functions lock the event_requests row FOR UPDATE, the same
-- lock the coordinator-assignment and status-transition functions take
-- (0014/0026), so a reassignment or cancellation cannot interleave: the
-- coordinator, status, requirement and suitability checks all see the locked
-- state at write time. Staff skill tags are seeded by SQL
-- (seed_technical_support_skills.sql); a screen to maintain them is a separate
-- story. Server-only: browser roles can neither call the functions nor read
-- the tables.

CREATE TABLE IF NOT EXISTS public.technical_support_requirements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_request_id uuid NOT NULL
        REFERENCES public.event_requests (id) ON DELETE CASCADE,
    description varchar NOT NULL
        CONSTRAINT technical_support_requirements_description_not_blank
        CHECK (btrim(description) <> '' AND char_length(description) <= 2000),
    skill_tag varchar NOT NULL
        CONSTRAINT technical_support_requirements_skill_tag_known
        CHECK (skill_tag IN ('audio_visual', 'lighting', 'it_network', 'livestream')),
    recorded_by varchar(64) NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    -- Names the (requirement, event) pair so an assignment can reference both
    -- columns and can never be filed under a different event than the
    -- requirement's own.
    CONSTRAINT technical_support_requirements_id_event_key
        UNIQUE (id, event_request_id)
);

-- Serves the per-event read the event page renders, in its stable order.
CREATE INDEX IF NOT EXISTS technical_support_requirements_event_idx
    ON public.technical_support_requirements (event_request_id, recorded_at, id);

-- Fixed vocabulary of staff skills; maintained by SQL seed, not by the app.
CREATE TABLE IF NOT EXISTS public.technical_support_skills (
    user_id varchar(64) NOT NULL,
    skill_tag varchar NOT NULL
        CONSTRAINT technical_support_skills_skill_tag_known
        CHECK (skill_tag IN ('audio_visual', 'lighting', 'it_network', 'livestream')),
    PRIMARY KEY (user_id, skill_tag)
);

CREATE TABLE IF NOT EXISTS public.technical_support_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id uuid NOT NULL,
    -- Denormalised from the requirement so the per-event read needs no join.
    -- The composite foreign key below pairs it with the requirement, so the
    -- copy can never disagree with the requirement's own event.
    event_request_id uuid NOT NULL
        REFERENCES public.event_requests (id) ON DELETE CASCADE,
    staff_id varchar(64) NOT NULL,
    assigned_by varchar(64) NOT NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT technical_support_assignments_once UNIQUE (requirement_id, staff_id),
    CONSTRAINT technical_support_assignments_requirement_event_fkey
        FOREIGN KEY (requirement_id, event_request_id)
        REFERENCES public.technical_support_requirements (id, event_request_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS technical_support_assignments_event_idx
    ON public.technical_support_assignments (event_request_id, assigned_at, id);

ALTER TABLE public.technical_support_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.technical_support_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.technical_support_assignments ENABLE ROW LEVEL SECURITY;

-- No policies: eventRequestService reaches these tables with the secret key,
-- which bypasses RLS. Enabling it with no policy denies anon and authenticated
-- by default, so a leaked publishable key cannot read who is supporting what.
REVOKE ALL ON public.technical_support_requirements FROM anon, authenticated;
REVOKE ALL ON public.technical_support_skills FROM anon, authenticated;
REVOKE ALL ON public.technical_support_assignments FROM anon, authenticated;
GRANT SELECT, INSERT ON public.technical_support_requirements TO service_role;
GRANT SELECT, INSERT ON public.technical_support_skills TO service_role;
GRANT SELECT, INSERT ON public.technical_support_assignments TO service_role;

CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO service_role;

-- One source of truth for "suitable", used by both the candidate list and the
-- assign function, so the list can never offer someone the write would refuse.
CREATE OR REPLACE FUNCTION private.is_suitable_technical_support(
    p_staff_id varchar,
    p_skill_tag varchar
)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.staff_roles
        WHERE user_id::text = p_staff_id
          AND role = 'technical_support'
    )
    AND EXISTS (
        SELECT 1
        FROM public.technical_support_skills
        WHERE user_id = p_staff_id
          AND skill_tag = p_skill_tag
    );
$$;

REVOKE ALL ON FUNCTION private.is_suitable_technical_support(varchar, varchar)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.is_suitable_technical_support(varchar, varchar)
    TO service_role;

CREATE OR REPLACE FUNCTION record_technical_support_requirement(
    p_event_request_id uuid,
    p_coordinator_id varchar,
    p_description text,
    p_skill_tag varchar
)
RETURNS public.technical_support_requirements
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_latest_coordinator varchar;
    v_requirement public.technical_support_requirements;
BEGIN
    SELECT * INTO v_event
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
        RAISE EXCEPTION 'caller is not the assigned coordinator'
            USING ERRCODE = 'P0003';
    END IF;

    IF v_event.status NOT IN ('Approved', 'Planning', 'Confirmed') THEN
        RAISE EXCEPTION 'technical support not allowed from status %', v_event.status
            USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO public.technical_support_requirements
        (event_request_id, description, skill_tag, recorded_by)
    VALUES
        (p_event_request_id, p_description, p_skill_tag, p_coordinator_id)
    RETURNING * INTO v_requirement;

    RETURN v_requirement;
END;
$$;

CREATE OR REPLACE FUNCTION assign_technical_support_staff(
    p_event_request_id uuid,
    p_requirement_id uuid,
    p_staff_id varchar,
    p_coordinator_id varchar
)
RETURNS public.technical_support_assignments
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_latest_coordinator varchar;
    v_requirement public.technical_support_requirements;
    v_assignment public.technical_support_assignments;
BEGIN
    SELECT * INTO v_event
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
        RAISE EXCEPTION 'caller is not the assigned coordinator'
            USING ERRCODE = 'P0003';
    END IF;

    IF v_event.status NOT IN ('Approved', 'Planning', 'Confirmed') THEN
        RAISE EXCEPTION 'technical support not allowed from status %', v_event.status
            USING ERRCODE = 'P0004';
    END IF;

    SELECT * INTO v_requirement
    FROM public.technical_support_requirements
    WHERE id = p_requirement_id;

    IF v_requirement.id IS NULL
        OR v_requirement.event_request_id <> p_event_request_id
    THEN
        RAISE EXCEPTION 'technical support requirement not found'
            USING ERRCODE = 'P0002';
    END IF;

    IF NOT private.is_suitable_technical_support(p_staff_id, v_requirement.skill_tag) THEN
        RAISE EXCEPTION 'staff member is not suitable' USING ERRCODE = 'P0005';
    END IF;

    -- A repeat assignment of the same person is rejected here by
    -- technical_support_assignments_once (23505).
    INSERT INTO public.technical_support_assignments
        (requirement_id, event_request_id, staff_id, assigned_by)
    VALUES
        (p_requirement_id, p_event_request_id, p_staff_id, p_coordinator_id)
    RETURNING * INTO v_assignment;

    RETURN v_assignment;
END;
$$;

CREATE OR REPLACE FUNCTION list_technical_support_candidates(p_requirement_id uuid)
RETURNS TABLE (staff_id varchar, already_assigned boolean)
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT sr.user_id::text,
           EXISTS (
               SELECT 1
               FROM public.technical_support_assignments a
               WHERE a.requirement_id = p_requirement_id
                 AND a.staff_id = sr.user_id::text
           )
    FROM public.staff_roles sr
    WHERE sr.role = 'technical_support'
      AND private.is_suitable_technical_support(
              sr.user_id::text,
              (
                  SELECT r.skill_tag
                  FROM public.technical_support_requirements r
                  WHERE r.id = p_requirement_id
              )
          )
    ORDER BY 1 ASC;
$$;

-- The service calls these through its server-only key; no role inherits them
-- through PUBLIC or Supabase's default per-role grants (0013).
REVOKE EXECUTE ON FUNCTION record_technical_support_requirement(uuid, varchar, text, varchar)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION record_technical_support_requirement(uuid, varchar, text, varchar)
    TO service_role;
REVOKE EXECUTE ON FUNCTION assign_technical_support_staff(uuid, uuid, varchar, varchar)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION assign_technical_support_staff(uuid, uuid, varchar, varchar)
    TO service_role;
REVOKE EXECUTE ON FUNCTION list_technical_support_candidates(uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION list_technical_support_candidates(uuid)
    TO service_role;
