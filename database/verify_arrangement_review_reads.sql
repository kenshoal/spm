-- AC5-X5 (cross-cutting): persisted review evidence must be event-scoped,
-- deterministic and server-readable without browser access or invalid records.
-- Run after the SCRUM-64 read-schema migration using an isolated privileged
-- fixture connection: psql -X -v ON_ERROR_STOP=1 -f <this file>.
-- Requires the real event schema, roles and one disposable auth.users identity.
-- This proves schema/read boundaries only, not trigger/clear/readiness workflows.
BEGIN;

DO $$
DECLARE
    v_actor uuid;
    v_event uuid;
    v_other uuid;
    v_role text;
    v_count integer;
BEGIN
    ASSERT to_regclass('public.arrangement_reviews') IS NOT NULL,
        'AC5-X5: missing arrangement_reviews read schema';
    SELECT id INTO v_actor FROM auth.users ORDER BY id LIMIT 1;
    ASSERT v_actor IS NOT NULL, 'AC5-X5: disposable auth fixture required';
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_actor, 'VERIFY SCRUM-64 read E1', 'Draft') RETURNING id INTO v_event;
    INSERT INTO public.event_requests (organiser_id, event_name, status)
        VALUES (v_actor, 'VERIFY SCRUM-64 read E2', 'Draft') RETURNING id INTO v_other;
    PERFORM set_config('scrum64.read_event', v_event::text, true);

    -- One actual trigger may affect two different arrangements/domains.
    INSERT INTO public.arrangement_reviews
        (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,
         changed_fields,reason,raised_at,cleared_at,cleared_by)
    VALUES
        ('00000000-0064-4000-8000-000000000001',v_event,'venue_booking',
         '10000000-0064-4000-8000-000000000001','20000000-0064-4000-8000-000000000001',
         'event_change',ARRAY['expected_attendance'],'Attendance changed',
         '2026-10-14 23:30:00-02',NULL,NULL),
        ('00000000-0064-4000-8000-000000000002',v_event,'equipment_reservation',
         '10000000-0064-4000-8000-000000000002','20000000-0064-4000-8000-000000000001',
         'event_change',ARRAY['expected_attendance'],'Same change affects equipment',
         '2026-10-15 01:00:00+00',NULL,NULL),
        ('00000000-0064-4000-8000-000000000003',v_event,'equipment_reservation',
         '10000000-0064-4000-8000-000000000002','20000000-0064-4000-8000-000000000003',
         'equipment_unavailable',ARRAY[]::text[],'Microphone unavailable',
         '2026-10-15 09:00:00+08',NULL,NULL),
        ('00000000-0064-4000-8000-000000000004',v_event,'venue_booking',
         '10000000-0064-4000-8000-000000000001','20000000-0064-4000-8000-000000000004',
         'safety_recheck',ARRAY[]::text[],'Safety recheck completed',
         '2026-10-15 01:00:00+00','2026-10-15 02:00:00+00',v_actor),
        ('00000000-0064-4000-8000-000000000009',v_other,'venue_booking',
         '10000000-0064-4000-8000-000000000009','20000000-0064-4000-8000-000000000009',
         'safety_recheck',ARRAY[]::text[],'Other event private reason',
         '2026-10-15 03:00:00+00',NULL,NULL);

    -- Invalid identity and clearing combinations must never enter durable state.
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
        VALUES (gen_random_uuid(),v_event,'invalid_domain',gen_random_uuid(),gen_random_uuid(),
                'event_change',ARRAY[]::text[],'Invalid domain',TIMESTAMPTZ '2026-10-15 01:00:00+00');
        RAISE EXCEPTION 'AC5-X5: invalid arrangement accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
        VALUES (gen_random_uuid(),v_event,'venue_booking',gen_random_uuid(),gen_random_uuid(),
                'invalid_trigger',ARRAY[]::text[],'Invalid trigger',TIMESTAMPTZ '2026-10-15 01:00:00+00');
        RAISE EXCEPTION 'AC5-X5: invalid trigger accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
        VALUES (gen_random_uuid(),v_event,'venue_booking',gen_random_uuid(),gen_random_uuid(),
                'event_change',ARRAY[]::text[],'   ',TIMESTAMPTZ '2026-10-15 01:00:00+00');
        RAISE EXCEPTION 'AC5-X5: blank reason accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at,
             cleared_at)
        VALUES (gen_random_uuid(),v_event,'venue_booking',gen_random_uuid(),gen_random_uuid(),
                'event_change',ARRAY[]::text[],'Missing cleared actor',TIMESTAMPTZ '2026-10-15 01:00:00+00',CURRENT_TIMESTAMP);
        RAISE EXCEPTION 'AC5-X5: unpaired cleared_at accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at,
             cleared_by)
        VALUES (gen_random_uuid(),v_event,'venue_booking',gen_random_uuid(),gen_random_uuid(),
                'event_change',ARRAY[]::text[],'Missing cleared time',TIMESTAMPTZ '2026-10-15 01:00:00+00',v_actor);
        RAISE EXCEPTION 'AC5-X5: unpaired cleared_by accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
        SELECT gen_random_uuid(),event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at
        FROM public.arrangement_reviews WHERE id='00000000-0064-4000-8000-000000000001';
        RAISE EXCEPTION 'AC5-X5: duplicate per-arrangement trigger accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
        VALUES (gen_random_uuid(),'ffffffff-0064-4000-8000-000000000099','venue_booking',
                gen_random_uuid(),gen_random_uuid(),'event_change',ARRAY[]::text[],'Missing event',TIMESTAMPTZ '2026-10-15 01:00:00+00');
        RAISE EXCEPTION 'AC5-X5: missing event FK accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.arrangement_reviews
            (id,event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason,raised_at)
        VALUES (gen_random_uuid(),v_event,'venue_booking',gen_random_uuid(),NULL,'event_change',ARRAY[]::text[],'Missing trigger',TIMESTAMPTZ '2026-10-15 01:00:00+00');
        RAISE EXCEPTION 'AC5-X5: null trigger accepted';
    EXCEPTION WHEN not_null_violation THEN NULL;
    END;
    SELECT count(*) INTO v_count FROM public.arrangement_reviews
        WHERE event_request_id IN(v_event,v_other);
    ASSERT v_count=5, 'AC5-X5: invalid writes left partial rows';
    ASSERT (SELECT relrowsecurity FROM pg_class
            WHERE oid='public.arrangement_reviews'::regclass), 'AC5-X5: RLS disabled';
    FOREACH v_role IN ARRAY ARRAY['anon','authenticated'] LOOP
        ASSERT NOT has_table_privilege(v_role,'public.arrangement_reviews',
            'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
            'AC5-X5: browser role has table privilege';
    END LOOP;
    ASSERT has_table_privilege('service_role','public.arrangement_reviews','SELECT'),
        'AC5-X5: service read denied';
    ASSERT NOT has_table_privilege('service_role','public.arrangement_reviews',
        'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
        'AC5-X5: initial read-only service contract unexpectedly grants writes';
END $$;

-- Actual role access complements metadata checks; no browser SELECT reaches rows.
SET LOCAL ROLE anon;
DO $$ BEGIN
    BEGIN
        PERFORM count(*) FROM public.arrangement_reviews;
        RAISE EXCEPTION 'AC5-X5: anon read unexpectedly succeeded';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
RESET ROLE;
SET LOCAL ROLE authenticated;
DO $$ BEGIN
    BEGIN
        PERFORM count(*) FROM public.arrangement_reviews;
        RAISE EXCEPTION 'AC5-X5: authenticated read unexpectedly succeeded';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
RESET ROLE;

SET LOCAL ROLE service_role;
DO $$
DECLARE v_ids uuid[]; v_all integer; v_outstanding integer;
BEGIN
    SELECT count(*) INTO v_all FROM public.arrangement_reviews
        WHERE event_request_id=current_setting('scrum64.read_event')::uuid;
    ASSERT v_all=4, 'AC5-X5: service raw event history is incomplete';
    SELECT array_agg(id ORDER BY raised_at DESC,id DESC),count(*)
        INTO v_ids,v_outstanding FROM public.arrangement_reviews
        WHERE event_request_id=current_setting('scrum64.read_event')::uuid
          AND cleared_at IS NULL;
    ASSERT v_ids=ARRAY['00000000-0064-4000-8000-000000000001'::uuid,
                      '00000000-0064-4000-8000-000000000003'::uuid,
                      '00000000-0064-4000-8000-000000000002'::uuid],
        'AC5-X5: event scope, absolute-time/ID order or outstanding predicate wrong';
    ASSERT v_outstanding=3, 'AC5-X5: stored outstanding truth inconsistent';
    RAISE NOTICE 'AC5-X5 arrangement review read-schema verification PASSED';
END $$;
RESET ROLE;
ROLLBACK;
