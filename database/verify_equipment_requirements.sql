-- Behavioural verification for equipment_requirements and
-- transition_equipment_requirement (SCRUM-33).
--
-- Run in the Supabase SQL Editor AFTER applying migration 0021. Before the
-- migration it stops before AC1-H1 with
--   42P01: relation "public.equipment_requirements" does not exist
-- which is the expected Red. Everything runs in one transaction and is rolled
-- back, so no data is left behind. Every case raises an exception naming its
-- ID when it fails; a run that reaches the final NOTICE has passed every case.
--
-- Test-case IDs trace to docs/testcases/scrum_33_testcases.md.
-- Needs at least one row in auth.users (run seed_test_accounts.sql first).

BEGIN;

-- Runs p_sql and passes only if it fails with SQLSTATE p_state. The failed
-- statement is undone by the block's implicit savepoint.
CREATE FUNCTION pg_temp.expect_sqlstate(p_case text, p_sql text, p_state text)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
    -- P0004 is PostgreSQL's assert_failure, which WHEN OTHERS does not catch;
    -- the team uses it for refused transitions, so it is listed explicitly.
    EXCEPTION WHEN assert_failure OR OTHERS THEN
        IF SQLSTATE <> p_state THEN
            RAISE EXCEPTION '% FAILED: expected SQLSTATE %, got % (%)',
                p_case, p_state, SQLSTATE, SQLERRM;
        END IF;
        RETURN;
    END;
    RAISE EXCEPTION '% FAILED: expected SQLSTATE %, but the statement succeeded',
        p_case, p_state;
END;
$$;

-- Inserts a requirement in the given status with consistent audit fields.
CREATE FUNCTION pg_temp.new_requirement(p_event uuid, p_user uuid, p_status text)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO public.equipment_requirements
        (event_request_id, equipment_type, quantity, recorded_by,
         status, updated_by, updated_at)
    VALUES
        (p_event, 'VERIFY-Projector', 2, p_user, p_status,
         CASE WHEN p_status = 'requested' THEN NULL ELSE p_user END,
         CASE WHEN p_status = 'requested' THEN NULL ELSE now() END)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

DO $$
DECLARE
    v_user uuid;
    v_staff uuid := '33333333-3333-3333-3333-333333333333';
    v_missing uuid := '99999999-9999-4999-8999-999999999999';
    v_event uuid;
    v_id uuid;
    v_before public.equipment_requirements%ROWTYPE;
    v_row public.equipment_requirements%ROWTYPE;
    v_fn constant text :=
        'public.transition_equipment_requirement(uuid, character varying, character varying, text, uuid)';
    v_case record;
    v_ok boolean;
BEGIN
    SELECT id INTO v_user FROM auth.users LIMIT 1;
    IF v_user IS NULL THEN
        RAISE EXCEPTION 'verify: needs at least one auth.users row (run seed_test_accounts.sql)';
    END IF;

    INSERT INTO public.event_requests (organiser_id, event_name)
    VALUES (v_user, 'VERIFY SCRUM-33 event')
    RETURNING id INTO v_event;

    -- AC1-H1 (happy): a minimal row is stored with its defaults
    INSERT INTO public.equipment_requirements
        (event_request_id, equipment_type, quantity, recorded_by)
    VALUES (v_event, 'VERIFY-Projector', 1, v_user)
    RETURNING * INTO v_row;
    IF v_row.status <> 'requested' OR v_row.recorded_at IS NULL
       OR v_row.technical_requirements IS NOT NULL OR v_row.support_note IS NOT NULL
       OR v_row.updated_by IS NOT NULL OR v_row.updated_at IS NOT NULL
       OR v_row.event_date_times <> '{}'::timestamptz[] THEN
        RAISE EXCEPTION 'AC1-H1 FAILED: unexpected defaults %', row_to_json(v_row);
    END IF;

    -- AC1-H2 (happy): technical requirements and the event snapshot round-trip unchanged
    INSERT INTO public.equipment_requirements
        (event_request_id, equipment_type, quantity, technical_requirements,
         event_name, event_date_times, recorded_by)
    VALUES (v_event, 'VERIFY-Projector', 2, 'HDMI, 4K', 'Annual Gala',
            ARRAY['2027-03-15T09:00:00+08:00', '2027-03-16T09:00:00+08:00']::timestamptz[],
            v_user)
    RETURNING id INTO v_id;
    SELECT * INTO v_row FROM public.equipment_requirements WHERE id = v_id;
    IF v_row.technical_requirements <> 'HDMI, 4K' OR v_row.event_name <> 'Annual Gala'
       OR v_row.event_date_times <> ARRAY['2027-03-15T09:00:00+08:00',
                                          '2027-03-16T09:00:00+08:00']::timestamptz[] THEN
        RAISE EXCEPTION 'AC1-H2 FAILED: stored values changed %', row_to_json(v_row);
    END IF;

    -- AC1-N1 (negative): a requirement for an unknown event is refused
    PERFORM pg_temp.expect_sqlstate('AC1-N1', format(
        'INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) VALUES (%L, %L, 1, %L)',
        v_missing, 'VERIFY-Projector', v_user), '23503');

    -- AC1-N2 to AC1-N5 (negative): each required column must be present
    FOR v_case IN
        SELECT * FROM (VALUES
            ('AC1-N2', format('INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) VALUES (NULL, %L, 1, %L)', 'VERIFY-Projector', v_user)),
            ('AC1-N3', format('INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) VALUES (%L, NULL, 1, %L)', v_event, v_user)),
            ('AC1-N4', format('INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) VALUES (%L, %L, NULL, %L)', v_event, 'VERIFY-Projector', v_user)),
            ('AC1-N5', format('INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) VALUES (%L, %L, 1, NULL)', v_event, 'VERIFY-Projector'))
        ) AS c(id, sql)
    LOOP
        PERFORM pg_temp.expect_sqlstate(v_case.id, v_case.sql, '23502');
    END LOOP;

    -- AC1-X1 (cross-cutting): an event that has requirements cannot be deleted
    PERFORM pg_temp.expect_sqlstate('AC1-X1',
        format('DELETE FROM public.event_requests WHERE id = %L', v_event), '23503');
    IF NOT EXISTS (SELECT 1 FROM public.event_requests WHERE id = v_event) THEN
        RAISE EXCEPTION 'AC1-X1 FAILED: the event was deleted';
    END IF;

    -- AC2-B1 (boundary): quantity 0, just below the minimum, is refused
    PERFORM pg_temp.expect_sqlstate('AC2-B1', format(
        'INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) VALUES (%L, %L, 0, %L)',
        v_event, 'VERIFY-Projector', v_user), '23514');

    -- AC2-B2 (boundary): quantity 1, the minimum, is accepted
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
    VALUES (v_event, 'VERIFY-Projector', 1, v_user);

    -- AC2-B3 (boundary): quantity 2, just above the minimum, is accepted
    INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
    VALUES (v_event, 'VERIFY-Projector', 2, v_user);

    -- AC2-N1 (negative): a blank equipment type is refused
    PERFORM pg_temp.expect_sqlstate('AC2-N1', format(
        'INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) VALUES (%L, %L, 1, %L)',
        v_event, '   ', v_user), '23514');

    -- AC2-B4 (boundary): technical requirements of exactly 2,000 characters are accepted
    INSERT INTO public.equipment_requirements
        (event_request_id, equipment_type, quantity, technical_requirements, recorded_by)
    VALUES (v_event, 'VERIFY-Projector', 1, repeat('x', 2000), v_user);

    -- AC2-B5 (boundary): technical requirements of 2,001 characters are refused
    PERFORM pg_temp.expect_sqlstate('AC2-B5', format(
        'INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, technical_requirements, recorded_by) VALUES (%L, %L, 1, %L, %L)',
        v_event, 'VERIFY-Projector', repeat('x', 2001), v_user), '23514');

    -- AC5-P1 to AC5-P3 (partition): each status value is storable with consistent audit fields
    PERFORM pg_temp.new_requirement(v_event, v_user, 'requested');
    PERFORM pg_temp.new_requirement(v_event, v_user, 'in_progress');
    PERFORM pg_temp.new_requirement(v_event, v_user, 'arranged');

    -- AC5-N1 (negative): an unknown status is refused
    PERFORM pg_temp.expect_sqlstate('AC5-N1',
        format('SELECT pg_temp.new_requirement(%L, %L, %L)', v_event, v_user, 'cancelled'),
        '23514');

    -- AC5-N2 (negative): a non-requested status without updated_by is refused
    PERFORM pg_temp.expect_sqlstate('AC5-N2', format(
        'INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by, status, updated_at) VALUES (%L, %L, 1, %L, %L, now())',
        v_event, 'VERIFY-Projector', v_user, 'in_progress'), '23514');

    -- AC5-N3 (negative): updated_by without updated_at is refused
    PERFORM pg_temp.expect_sqlstate('AC5-N3', format(
        'INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by, status, updated_by) VALUES (%L, %L, 1, %L, %L, %L)',
        v_event, 'VERIFY-Projector', v_user, 'in_progress', v_staff), '23514');

    -- AC5-H1 (happy): the function moves requested to in_progress and records who and when
    v_id := pg_temp.new_requirement(v_event, v_user, 'requested');
    SELECT * INTO v_before FROM public.equipment_requirements WHERE id = v_id;
    SELECT * INTO v_row
    FROM public.transition_equipment_requirement(v_id, 'requested', 'in_progress', 'Sourcing spare', v_staff);
    IF v_row.id <> v_id OR v_row.status <> 'in_progress' OR v_row.support_note <> 'Sourcing spare'
       OR v_row.updated_by <> v_staff OR v_row.updated_at IS NULL
       OR v_row.equipment_type <> v_before.equipment_type OR v_row.quantity <> v_before.quantity
       OR v_row.recorded_by <> v_before.recorded_by
       OR v_row.event_name IS DISTINCT FROM v_before.event_name THEN
        RAISE EXCEPTION 'AC5-H1 FAILED: %', row_to_json(v_row);
    END IF;
    SELECT * INTO v_row FROM public.equipment_requirements WHERE id = v_id;
    IF v_row.status <> 'in_progress' OR v_row.updated_by <> v_staff THEN
        RAISE EXCEPTION 'AC5-H1 FAILED: change not stored %', row_to_json(v_row);
    END IF;

    -- AC5-P4 to AC5-P7 (partition): every other allowed transition succeeds
    FOR v_case IN
        SELECT * FROM (VALUES
            ('AC5-P4', 'requested',   'arranged',    NULL),
            ('AC5-P5', 'in_progress', 'arranged',    NULL),
            ('AC5-P6', 'arranged',    'in_progress', 'Supplier cancelled'),
            ('AC5-P7', 'in_progress', 'in_progress', 'Spare found in Store Room B')
        ) AS c(id, from_status, to_status, note)
    LOOP
        v_id := pg_temp.new_requirement(v_event, v_user, v_case.from_status);
        SELECT * INTO v_row FROM public.transition_equipment_requirement(
            v_id, v_case.from_status, v_case.to_status, v_case.note, v_staff);
        IF v_row.status <> v_case.to_status OR v_row.updated_by <> v_staff
           OR (v_case.note IS NOT NULL AND v_row.support_note <> v_case.note) THEN
            RAISE EXCEPTION '% FAILED: %', v_case.id, row_to_json(v_row);
        END IF;
    END LOOP;

    -- AC5-N4 to AC5-N7 (negative): disallowed transitions are refused and change nothing
    FOR v_case IN
        SELECT * FROM (VALUES
            ('AC5-N4', 'requested',   'requested'),
            ('AC5-N5', 'arranged',    'arranged'),
            ('AC5-N6', 'in_progress', 'requested'),
            ('AC5-N7', 'arranged',    'requested')
        ) AS c(id, from_status, to_status)
    LOOP
        v_id := pg_temp.new_requirement(v_event, v_user, v_case.from_status);
        SELECT * INTO v_before FROM public.equipment_requirements WHERE id = v_id;
        PERFORM pg_temp.expect_sqlstate(v_case.id, format(
            'SELECT public.transition_equipment_requirement(%L, %L, %L, %L, %L)',
            v_id, v_case.from_status, v_case.to_status, 'note', v_staff), 'P0004');
        SELECT * INTO v_row FROM public.equipment_requirements WHERE id = v_id;
        IF row_to_json(v_row)::text <> row_to_json(v_before)::text THEN
            RAISE EXCEPTION '% FAILED: row changed', v_case.id;
        END IF;
    END LOOP;

    -- AC5-N8 (negative): an update that expects a status the row no longer has is refused
    v_id := pg_temp.new_requirement(v_event, v_user, 'in_progress');
    SELECT * INTO v_before FROM public.equipment_requirements WHERE id = v_id;
    PERFORM pg_temp.expect_sqlstate('AC5-N8', format(
        'SELECT public.transition_equipment_requirement(%L, %L, %L, NULL, %L)',
        v_id, 'requested', 'arranged', v_staff), 'P0004');
    SELECT * INTO v_row FROM public.equipment_requirements WHERE id = v_id;
    IF row_to_json(v_row)::text <> row_to_json(v_before)::text THEN
        RAISE EXCEPTION 'AC5-N8 FAILED: row changed';
    END IF;

    -- AC5-N9 (negative): an unknown requirement is reported as not found
    PERFORM pg_temp.expect_sqlstate('AC5-N9', format(
        'SELECT public.transition_equipment_requirement(%L, %L, %L, NULL, %L)',
        v_missing, 'requested', 'in_progress', v_staff), 'P0002');

    -- AC5-N10 (negative): a note-only update needs a non-blank note
    v_id := pg_temp.new_requirement(v_event, v_user, 'in_progress');
    SELECT * INTO v_before FROM public.equipment_requirements WHERE id = v_id;
    PERFORM pg_temp.expect_sqlstate('AC5-N10 (null note)', format(
        'SELECT public.transition_equipment_requirement(%L, %L, %L, NULL, %L)',
        v_id, 'in_progress', 'in_progress', v_staff), 'P0004');
    PERFORM pg_temp.expect_sqlstate('AC5-N10 (blank note)', format(
        'SELECT public.transition_equipment_requirement(%L, %L, %L, %L, %L)',
        v_id, 'in_progress', 'in_progress', '   ', v_staff), 'P0004');
    SELECT * INTO v_row FROM public.equipment_requirements WHERE id = v_id;
    IF row_to_json(v_row)::text <> row_to_json(v_before)::text THEN
        RAISE EXCEPTION 'AC5-N10 FAILED: row changed';
    END IF;

    -- AC5-X1 (cross-cutting): a support note over 2,000 characters is refused and changes nothing
    v_id := pg_temp.new_requirement(v_event, v_user, 'requested');
    SELECT * INTO v_before FROM public.equipment_requirements WHERE id = v_id;
    PERFORM pg_temp.expect_sqlstate('AC5-X1', format(
        'SELECT public.transition_equipment_requirement(%L, %L, %L, %L, %L)',
        v_id, 'requested', 'in_progress', repeat('x', 2001), v_staff), '23514');
    SELECT * INTO v_row FROM public.equipment_requirements WHERE id = v_id;
    IF row_to_json(v_row)::text <> row_to_json(v_before)::text THEN
        RAISE EXCEPTION 'AC5-X1 FAILED: row changed';
    END IF;

    -- AC5-X2 (cross-cutting): the function locks the row it changes
    IF pg_get_functiondef(v_fn::regprocedure) NOT ILIKE '%FOR UPDATE%' THEN
        RAISE EXCEPTION 'AC5-X2 FAILED: transition_equipment_requirement takes no row lock';
    END IF;

    -- AC4-X1 (cross-cutting): the per-event and queue lookup indexes exist
    IF NOT EXISTS (SELECT 1 FROM pg_indexes
                   WHERE schemaname = 'public' AND tablename = 'equipment_requirements'
                     AND indexdef ILIKE '%(event_request_id, recorded_at, id)%')
       OR NOT EXISTS (SELECT 1 FROM pg_indexes
                      WHERE schemaname = 'public' AND tablename = 'equipment_requirements'
                        AND indexdef ILIKE '%(status, recorded_at, id)%') THEN
        RAISE EXCEPTION 'AC4-X1 FAILED: lookup indexes missing';
    END IF;

    -- AC6-X1 (cross-cutting): browser roles hold no privilege on the table
    FOR v_case IN
        SELECT r AS role, p AS privilege
        FROM unnest(ARRAY['anon', 'authenticated']) AS r,
             unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS p
    LOOP
        IF has_table_privilege(v_case.role, 'public.equipment_requirements', v_case.privilege) THEN
            RAISE EXCEPTION 'AC6-X1 FAILED: % has %', v_case.role, v_case.privilege;
        END IF;
    END LOOP;

    -- AC6-X2 (cross-cutting): row-level security is enabled
    SELECT relrowsecurity INTO v_ok FROM pg_class
    WHERE oid = 'public.equipment_requirements'::regclass;
    IF NOT v_ok THEN
        RAISE EXCEPTION 'AC6-X2 FAILED: row-level security is off';
    END IF;

    -- AC6-X3 (cross-cutting): the service role can read, insert and update
    IF NOT (has_table_privilege('service_role', 'public.equipment_requirements', 'SELECT')
            AND has_table_privilege('service_role', 'public.equipment_requirements', 'INSERT')
            AND has_table_privilege('service_role', 'public.equipment_requirements', 'UPDATE')) THEN
        RAISE EXCEPTION 'AC6-X3 FAILED: service_role is missing a privilege';
    END IF;

    -- AC6-X4 (cross-cutting): only the service role may execute the transition function
    IF has_function_privilege('anon', v_fn, 'EXECUTE')
       OR has_function_privilege('authenticated', v_fn, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_fn, 'EXECUTE') THEN
        RAISE EXCEPTION 'AC6-X4 FAILED: function execute grants are wrong';
    END IF;

    RAISE NOTICE 'SCRUM-33 verify: all equipment_requirements cases passed';
END;
$$;

ROLLBACK;
