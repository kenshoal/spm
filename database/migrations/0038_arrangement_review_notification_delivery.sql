-- SCRUM-64: durable per-recipient delivery progress and current recipient facts.
ALTER TABLE public.arrangement_review_notification_outbox
    ADD COLUMN accepted_recipients jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN last_attempted_at timestamptz;
DROP INDEX public.arrangement_review_notification_pending_idx;
CREATE INDEX arrangement_review_notification_pending_idx
    ON public.arrangement_review_notification_outbox
        (last_attempted_at ASC NULLS FIRST, occurred_at, review_id)
    WHERE published_at IS NULL;

-- Private facts resolver: existing accounts only, with the auth service's role
-- precedence. Aggregate in SQL so REST directory page limits cannot drop staff.
CREATE OR REPLACE FUNCTION private.arrangement_review_notification_recipients(
    p_event_request_id uuid, p_arrangement text, p_trigger_id uuid, p_trigger_type text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_result jsonb;
BEGIN
    WITH effective_accounts AS (
        SELECT u.id,
            CASE
                WHEN pg_catalog.cardinality(s.roles) > 0 THEN s.roles
                WHEN pg_catalog.cardinality(m.roles) > 0 THEN m.roles
                WHEN pg_catalog.jsonb_typeof(u.raw_app_meta_data -> 'role') = 'string'
                    AND u.raw_app_meta_data ->> 'role' <> ''
                    THEN ARRAY[u.raw_app_meta_data ->> 'role']
                ELSE ARRAY['attendee']::text[]
            END AS roles
        FROM auth.users AS u
        LEFT JOIN LATERAL (
            SELECT pg_catalog.array_agg(r.role::text) AS roles
            FROM public.staff_roles AS r WHERE r.user_id = u.id
        ) AS s ON true
        LEFT JOIN LATERAL (
            SELECT pg_catalog.array_agg(value #>> '{}') AS roles
            FROM pg_catalog.jsonb_array_elements(
                CASE WHEN pg_catalog.jsonb_typeof(u.raw_app_meta_data -> 'roles') = 'array'
                    THEN u.raw_app_meta_data -> 'roles' ELSE '[]'::jsonb END
            ) AS metadata_role(value)
            WHERE pg_catalog.jsonb_typeof(value) = 'string'
        ) AS m ON true
    ), current_assignment AS (
        SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
        WHERE a.event_request_id = p_event_request_id ORDER BY a.id DESC LIMIT 1
    )
    SELECT pg_catalog.jsonb_build_object(
        'recipients_available', true,
        'coordinator_id', (
            SELECT u.id FROM effective_accounts AS u
            JOIN current_assignment AS a ON u.id::text = a.coordinator_id
            WHERE 'event_coordinator' = ANY(u.roles)
        ),
        'domain_recipient_ids', COALESCE((
            SELECT pg_catalog.jsonb_agg(u.id ORDER BY u.id)
            FROM effective_accounts AS u
            WHERE (CASE p_arrangement WHEN 'venue_booking' THEN 'venue_staff'
                WHEN 'equipment_reservation' THEN 'technical_support' END) = ANY(u.roles)
        ), '[]'::jsonb),
        'change_request_id', (
            SELECT c.id FROM public.event_change_requests AS c
            WHERE p_trigger_type = 'event_change' AND c.id = p_trigger_id
                AND c.event_request_id = p_event_request_id AND c.status = 'Approved'
        )
    ) INTO v_result;
    RETURN v_result;
END;
$$;
REVOKE ALL ON FUNCTION private.arrangement_review_notification_recipients(uuid, text, uuid, text)
    FROM PUBLIC, anon, authenticated, service_role;

-- A narrow server-only definer owns progress updates; no direct table UPDATE
-- grant is needed. The immutable source snapshot remains untouched.
CREATE OR REPLACE FUNCTION public.begin_arrangement_review_notification_attempt(p_review_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_job public.arrangement_review_notification_outbox%ROWTYPE;
    v_recipients jsonb;
BEGIN
    SELECT * INTO v_job FROM public.arrangement_review_notification_outbox
    WHERE review_id = p_review_id FOR UPDATE;
    IF NOT FOUND OR v_job.published_at IS NOT NULL THEN RETURN NULL; END IF;
    UPDATE public.arrangement_review_notification_outbox
    SET last_attempted_at = pg_catalog.clock_timestamp() WHERE review_id = p_review_id;
    -- Keep the attempt stamp even when the directory is temporarily unavailable,
    -- so an unresolved oldest batch rotates instead of starving later work.
    BEGIN
        v_recipients := private.arrangement_review_notification_recipients(
            v_job.event_request_id, v_job.payload ->> 'arrangement',
            (v_job.payload ->> 'trigger_id')::uuid, v_job.payload ->> 'trigger_type');
    EXCEPTION WHEN OTHERS THEN
        RAISE LOG 'Arrangement notification recipient lookup failed (SQLSTATE %)', SQLSTATE;
        v_recipients := pg_catalog.jsonb_build_object(
            'recipients_available', false, 'coordinator_id', NULL,
            'domain_recipient_ids', '[]'::jsonb, 'change_request_id', NULL);
    END;
    RETURN pg_catalog.jsonb_build_object('review_id', v_job.review_id,
        'payload', v_job.payload, 'accepted_recipients', v_job.accepted_recipients)
        || v_recipients;
END;
$$;

CREATE OR REPLACE FUNCTION public.record_arrangement_review_notification_accepted(
    p_review_id uuid, p_recipient_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF p_recipient_id IS NULL THEN
        RAISE EXCEPTION 'Recipient is required' USING ERRCODE = '22023';
    END IF;
    -- The trusted relay calls this only after 202 acceptance. A single UPDATE
    -- serialises concurrent unions and preserves the first accepted timestamp,
    -- even if this recipient's role changes after the HTTP request.
    UPDATE public.arrangement_review_notification_outbox
    SET accepted_recipients = accepted_recipients || pg_catalog.jsonb_build_object(
        p_recipient_id::text, pg_catalog.clock_timestamp())
    WHERE review_id = p_review_id AND published_at IS NULL
        AND NOT accepted_recipients ? p_recipient_id::text;
END;
$$;

CREATE OR REPLACE FUNCTION public.complete_arrangement_review_notification(p_review_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_job public.arrangement_review_notification_outbox%ROWTYPE;
    v_recipients jsonb;
BEGIN
    SELECT * INTO v_job FROM public.arrangement_review_notification_outbox
    WHERE review_id = p_review_id FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    IF v_job.published_at IS NOT NULL THEN RETURN true; END IF;
    BEGIN
        v_recipients := private.arrangement_review_notification_recipients(
            v_job.event_request_id, v_job.payload ->> 'arrangement',
            (v_job.payload ->> 'trigger_id')::uuid, v_job.payload ->> 'trigger_type');
    EXCEPTION WHEN OTHERS THEN
        RAISE LOG 'Arrangement notification completion lookup failed (SQLSTATE %)', SQLSTATE;
        RETURN false;
    END;
    IF v_recipients ->> 'coordinator_id' IS NULL
        OR pg_catalog.jsonb_array_length(v_recipients -> 'domain_recipient_ids') = 0
        OR NOT v_job.accepted_recipients ? (v_recipients ->> 'coordinator_id')
        OR EXISTS (
            SELECT 1 FROM pg_catalog.jsonb_array_elements_text(
                v_recipients -> 'domain_recipient_ids') AS recipient(id)
            WHERE NOT v_job.accepted_recipients ? recipient.id
        ) THEN RETURN false; END IF;
    UPDATE public.arrangement_review_notification_outbox
    SET published_at = pg_catalog.clock_timestamp() WHERE review_id = p_review_id;
    RETURN true;
END;
$$;
REVOKE ALL ON FUNCTION public.begin_arrangement_review_notification_attempt(uuid),
    public.record_arrangement_review_notification_accepted(uuid, uuid),
    public.complete_arrangement_review_notification(uuid) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.begin_arrangement_review_notification_attempt(uuid),
    public.record_arrangement_review_notification_accepted(uuid, uuid),
    public.complete_arrangement_review_notification(uuid) TO service_role;
