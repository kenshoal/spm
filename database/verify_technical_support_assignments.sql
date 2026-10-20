-- Run after 0051_technical_support_assignments.sql (SCRUM-19). Every change is
-- rolled back, except nothing: BEGIN ... ROLLBACK throughout. Uses no DELETE or
-- UPDATE except restoring a status and a role it removed for one probe.
--   psql -X -v ON_ERROR_STOP=1 -f database/verify_technical_support_assignments.sql
-- On a disposable cluster built with:
--   python3 -I database/tests/bootstrap_safety_review.py --disposable \
--       --dsn postgresql://... --psql psql \
--       --through 0051_technical_support_assignments.sql
-- Case IDs refer to docs/testcases/scrum_19_testcases.md (D layer).

BEGIN;

DO $verify$
DECLARE
    v_event uuid := '11111111-1111-4111-8111-111111111111';
    v_other uuid := '22222222-2222-4222-8222-222222222222';
    v_coord varchar := '51000000-0000-4000-8000-000000000001';
    v_coord2 varchar := '51000000-0000-4000-8000-000000000002';
    v_tss_av varchar := '51000000-0000-4000-8000-000000000003';
    v_tss_av2 varchar := '51000000-0000-4000-8000-000000000004';
    v_tss_light varchar := '51000000-0000-4000-8000-000000000005';
    v_tss_none varchar := '51000000-0000-4000-8000-000000000006';
    v_venue_av varchar := '51000000-0000-4000-8000-000000000007';
    v_org uuid := '51000000-0000-4000-8000-000000000008';
    v_req uuid;
    v_req_probe uuid;
    v_req_other uuid;
    v_row public.technical_support_requirements%ROWTYPE;
    v_assignment public.technical_support_assignments%ROWTYPE;
    v_count int;
    v_text text;
    v_listed boolean;
    v_succeeded boolean;
    r record;
BEGIN
    -- Fixtures: users, roles, skills, two Planning events, one coordinator each.
    INSERT INTO auth.users (id) VALUES
        (v_coord::uuid), (v_coord2::uuid), (v_tss_av::uuid), (v_tss_av2::uuid),
        (v_tss_light::uuid), (v_tss_none::uuid), (v_venue_av::uuid), (v_org);
    INSERT INTO public.staff_roles (user_id, role) VALUES
        (v_coord::uuid, 'event_coordinator'),
        (v_coord2::uuid, 'event_coordinator'),
        (v_tss_av::uuid, 'technical_support'),
        (v_tss_av2::uuid, 'technical_support'),
        (v_tss_light::uuid, 'technical_support'),
        (v_tss_none::uuid, 'technical_support'),
        (v_venue_av::uuid, 'venue_staff'),
        (v_org, 'event_organiser');
    INSERT INTO public.technical_support_skills (user_id, skill_tag) VALUES
        (v_tss_av, 'audio_visual'), (v_tss_av, 'it_network'),
        (v_tss_av2, 'audio_visual'), (v_tss_light, 'lighting'),
        (v_venue_av, 'audio_visual');
    INSERT INTO public.event_requests (id, organiser_id, status, event_name) VALUES
        (v_event, v_org, 'Planning', 'Tech Summit 2030'),
        (v_other, v_org, 'Planning', 'Other Gathering');
    INSERT INTO public.event_coordinator_assignments
        (event_request_id, coordinator_id, assigned_by) VALUES
        (v_event, v_coord, v_coord), (v_other, v_coord, v_coord);

    -- AC2-X4: browser roles can neither execute the new functions nor read the
    -- new tables; service_role can.
    IF has_function_privilege('anon',
           'public.record_technical_support_requirement(uuid,varchar,text,varchar)',
           'EXECUTE')
        OR has_function_privilege('authenticated',
           'public.record_technical_support_requirement(uuid,varchar,text,varchar)',
           'EXECUTE')
        OR has_function_privilege('anon',
           'public.assign_technical_support_staff(uuid,uuid,varchar,varchar)', 'EXECUTE')
        OR has_function_privilege('authenticated',
           'public.assign_technical_support_staff(uuid,uuid,varchar,varchar)', 'EXECUTE')
        OR has_function_privilege('anon',
           'public.list_technical_support_candidates(uuid)', 'EXECUTE')
        OR has_function_privilege('authenticated',
           'public.list_technical_support_candidates(uuid)', 'EXECUTE')
        OR has_function_privilege('anon',
           'private.is_suitable_technical_support(varchar,varchar)', 'EXECUTE')
        OR has_function_privilege('authenticated',
           'private.is_suitable_technical_support(varchar,varchar)', 'EXECUTE')
    THEN
        RAISE EXCEPTION 'AC2-X4: a browser role can execute a new function';
    END IF;
    IF NOT has_function_privilege('service_role',
           'public.record_technical_support_requirement(uuid,varchar,text,varchar)',
           'EXECUTE')
        OR NOT has_function_privilege('service_role',
           'public.assign_technical_support_staff(uuid,uuid,varchar,varchar)', 'EXECUTE')
        OR NOT has_function_privilege('service_role',
           'public.list_technical_support_candidates(uuid)', 'EXECUTE')
        OR NOT has_function_privilege('service_role',
           'private.is_suitable_technical_support(varchar,varchar)', 'EXECUTE')
    THEN
        RAISE EXCEPTION 'AC2-X4: service_role cannot execute a new function';
    END IF;
    FOR r IN
        SELECT t.typname, p.privilege_type FROM (VALUES
            ('technical_support_requirements'), ('technical_support_skills'),
            ('technical_support_assignments')) AS t(typname),
            (VALUES ('SELECT'), ('INSERT')) AS p(privilege_type)
    LOOP
        IF has_table_privilege('anon', 'public.' || r.typname, r.privilege_type)
            OR has_table_privilege('authenticated', 'public.' || r.typname,
                                   r.privilege_type)
        THEN
            RAISE EXCEPTION 'AC2-X4: browser role has % on %', r.privilege_type,
                r.typname;
        END IF;
        IF NOT has_table_privilege('service_role', 'public.' || r.typname,
                                   r.privilege_type) THEN
            RAISE EXCEPTION 'AC2-X4: service_role lacks % on %', r.privilege_type,
                r.typname;
        END IF;
    END LOOP;

    -- AC1-H1: the assigned coordinator records a requirement, stored verbatim.
    SELECT * INTO v_row
    FROM public.record_technical_support_requirement(
             v_event, v_coord,
             'Two wireless mics and a mixing-desk operator for the keynote',
             'audio_visual');
    IF v_row.event_request_id <> v_event OR v_row.skill_tag <> 'audio_visual'
       OR v_row.recorded_by <> v_coord OR v_row.recorded_at IS NULL
       OR v_row.description <>
          'Two wireless mics and a mixing-desk operator for the keynote' THEN
        RAISE EXCEPTION 'AC1-H1: requirement stored wrong: %', v_row;
    END IF;
    v_req := v_row.id;

    -- AC1-P11..P14: each tag in the vocabulary is accepted.
    FOR r IN SELECT * FROM (VALUES ('lighting'), ('it_network'), ('livestream'))
             AS t(tag)
    LOOP
        PERFORM public.record_technical_support_requirement(
            v_event, v_coord, 'tag probe ' || r.tag, r.tag);
    END LOOP;

    -- AC1-B4: a description of exactly 2000 characters is accepted.
    PERFORM public.record_technical_support_requirement(
        v_event, v_coord, repeat('x', 2000), 'audio_visual');

    -- AC1-B5: one character over the limit is refused by the check constraint.
    BEGIN
        PERFORM public.record_technical_support_requirement(
            v_event, v_coord, repeat('x', 2001), 'audio_visual');
        RAISE EXCEPTION 'AC1-B5: 2001 characters accepted';
    EXCEPTION WHEN SQLSTATE '23514' THEN NULL;
    END;

    -- AC1-B1 (at the database too): a blank description is refused.
    BEGIN
        PERFORM public.record_technical_support_requirement(
            v_event, v_coord, '   ', 'audio_visual');
        RAISE EXCEPTION 'AC1-B1: blank description accepted';
    EXCEPTION WHEN SQLSTATE '23514' THEN NULL;
    END;

    -- AC1-N1 (at the database too): an unknown skill tag is refused.
    BEGIN
        PERFORM public.record_technical_support_requirement(
            v_event, v_coord, 'no such tag', 'plumbing');
        RAISE EXCEPTION 'AC1-N1: unknown tag accepted';
    EXCEPTION WHEN SQLSTATE '23514' THEN NULL;
    END;

    -- AC1-X2: a coordinator who is not the latest on the event is refused, and
    -- nothing is stored.
    BEGIN
        PERFORM public.record_technical_support_requirement(
            v_event, v_coord2, 'should not store', 'audio_visual');
        RAISE EXCEPTION 'AC1-X2: unrelated coordinator recorded';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;

    -- AC1-N5: an unknown event is refused.
    BEGIN
        PERFORM public.record_technical_support_requirement(
            gen_random_uuid(), v_coord, 'no event', 'audio_visual');
        RAISE EXCEPTION 'AC1-N5: unknown event accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;

    -- AC2-H1: a suitable staff member is assigned with the caller recorded.
    SELECT * INTO v_assignment
    FROM public.assign_technical_support_staff(v_event, v_req, v_tss_av, v_coord);
    IF v_assignment.requirement_id <> v_req
       OR v_assignment.event_request_id <> v_event
       OR v_assignment.staff_id <> v_tss_av
       OR v_assignment.assigned_by <> v_coord
       OR v_assignment.assigned_at IS NULL THEN
        RAISE EXCEPTION 'AC2-H1: assignment stored wrong: %', v_assignment;
    END IF;

    -- AC2-H2: several staff can be assigned to one requirement.
    PERFORM public.assign_technical_support_staff(v_event, v_req, v_tss_av2, v_coord);
    SELECT count(*) INTO v_count
    FROM public.technical_support_assignments WHERE requirement_id = v_req;
    IF v_count <> 2 THEN
        RAISE EXCEPTION 'AC2-H2: expected 2 assignments, found %', v_count;
    END IF;

    -- AC2-N3: the same person twice is refused by the unique constraint, from
    -- the function and from a direct insert; one row remains.
    BEGIN
        PERFORM public.assign_technical_support_staff(
            v_event, v_req, v_tss_av, v_coord);
        RAISE EXCEPTION 'AC2-N3: repeat assignment accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO public.technical_support_assignments
            (requirement_id, event_request_id, staff_id, assigned_by)
        VALUES (v_req, v_event, v_tss_av, v_coord);
        RAISE EXCEPTION 'AC2-N3: direct duplicate insert accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- AC3-P1: role and matching tag are suitable.
    IF NOT private.is_suitable_technical_support(v_tss_av, 'audio_visual') THEN
        RAISE EXCEPTION 'AC3-P1: role and tag judged unsuitable';
    END IF;

    -- AC3-P2: the role with a different tag is not suitable, and the assign
    -- function refuses.
    IF private.is_suitable_technical_support(v_tss_light, 'audio_visual') THEN
        RAISE EXCEPTION 'AC3-P2: wrong tag judged suitable';
    END IF;
    BEGIN
        PERFORM public.assign_technical_support_staff(v_event, v_req, v_tss_light, v_coord);
        RAISE EXCEPTION 'AC3-P2: wrong-tag staff assigned';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN NULL;
    END;

    -- AC3-P3: the role with no tags is not suitable.
    IF private.is_suitable_technical_support(v_tss_none, 'audio_visual') THEN
        RAISE EXCEPTION 'AC3-P3: untagged staff judged suitable';
    END IF;

    -- AC3-P4: the tag without the technical_support role is not suitable.
    IF private.is_suitable_technical_support(v_venue_av, 'audio_visual') THEN
        RAISE EXCEPTION 'AC3-P4: venue staff judged suitable';
    END IF;
    BEGIN
        PERFORM public.assign_technical_support_staff(v_event, v_req, v_venue_av, v_coord);
        RAISE EXCEPTION 'AC3-P4: venue staff assigned';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN NULL;
    END;

    -- AC3-N1: an unknown user is "not suitable", not an error, so the response
    -- cannot reveal whether the account exists.
    IF private.is_suitable_technical_support('ghost-user', 'audio_visual') THEN
        RAISE EXCEPTION 'AC3-N1: unknown user judged suitable';
    END IF;
    BEGIN
        PERFORM public.assign_technical_support_staff(v_event, v_req, 'ghost-user', v_coord);
        RAISE EXCEPTION 'AC3-N1: unknown user assigned';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN NULL;
    END;

    -- AC3-H1: the candidate list shows exactly the suitable staff, ascending,
    -- with the person already on the requirement marked.
    SELECT string_agg(staff_id || ':' || already_assigned::text, ', ' ORDER BY staff_id)
        INTO v_text
    FROM public.list_technical_support_candidates(v_req);
    IF v_text <> v_tss_av || ':true, ' || v_tss_av2 || ':false' THEN
        RAISE EXCEPTION 'AC3-H1: candidates are %', v_text;
    END IF;

    -- AC3-X1: no availability or double-booking check. The second event takes a
    -- requirement and the same staff member as the first event's keynote.
    SELECT * INTO v_row
    FROM public.record_technical_support_requirement(
             v_other, v_coord, 'Venue Wi-Fi for 300 delegates', 'it_network');
    v_req_other := v_row.id;
    SELECT * INTO v_assignment
    FROM public.assign_technical_support_staff(v_other, v_req_other, v_tss_av, v_coord);
    IF v_assignment.staff_id <> v_tss_av THEN
        RAISE EXCEPTION 'AC3-X1: double booking refused: %', v_assignment;
    END IF;

    -- AC2-N1: the requirement of the other event is refused through this
    -- event's path, and an unknown requirement id likewise.
    BEGIN
        PERFORM public.assign_technical_support_staff(
            v_event, v_req_other, v_tss_av2, v_coord);
        RAISE EXCEPTION 'AC2-N1: other event''s requirement accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;
    BEGIN
        PERFORM public.assign_technical_support_staff(
            v_event, gen_random_uuid(), v_tss_av2, v_coord);
        RAISE EXCEPTION 'AC2-N2: unknown requirement accepted';
    EXCEPTION WHEN SQLSTATE 'P0002' THEN NULL;
    END;

    -- AC2-N6 / AC2-P10 (database half): once the event is Cancelled the
    -- requirement stays, but assignment is refused; restoring Planning works.
    UPDATE public.event_requests SET status = 'Cancelled' WHERE id = v_other;
    BEGIN
        PERFORM public.assign_technical_support_staff(
            v_other, v_req_other, v_tss_av2, v_coord);
        RAISE EXCEPTION 'AC2-N6: cancelled event accepted an assignment';
    EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
    END;
    UPDATE public.event_requests SET status = 'Planning' WHERE id = v_other;

    -- AC2-N5: a coordinator replaced between page load and assign is refused —
    -- the latest assignment (highest id) decides, so v_coord is stale now.
    INSERT INTO public.event_coordinator_assignments
        (event_request_id, coordinator_id, assigned_by)
    VALUES (v_other, v_coord2, v_coord2);
    BEGIN
        PERFORM public.assign_technical_support_staff(
            v_other, v_req_other, v_tss_av2, v_coord);
        RAISE EXCEPTION 'AC2-N5: stale coordinator assigned';
    EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL;
    END;
    -- ...and the new coordinator can assign: the check reads the same state.
    PERFORM public.assign_technical_support_staff(v_other, v_req_other, v_tss_av2, v_coord2);

    -- AC3-P5: suitability is rechecked at write time — a staff member whose
    -- technical_support role is removed after tagging is refused.
    DELETE FROM public.staff_roles WHERE user_id = v_tss_av2::uuid;
    BEGIN
        PERFORM public.assign_technical_support_staff(
            v_event, v_req, v_tss_av2, v_coord);
        RAISE EXCEPTION 'AC3-P5: roleless staff assigned';
    EXCEPTION WHEN SQLSTATE 'P0005' THEN NULL;
    END;
    INSERT INTO public.staff_roles (user_id, role)
    VALUES (v_tss_av2::uuid, 'technical_support');

    -- AC3-X4: the candidate list and the assign function never disagree, per
    -- user, with each probe's write rolled back to its savepoint.
    SELECT id INTO v_req_probe
    FROM public.record_technical_support_requirement(
             v_event, v_coord, 'probe requirement', 'audio_visual');
    FOR r IN
        SELECT u AS staff_id FROM unnest(ARRAY[
            v_tss_av, v_tss_av2, v_tss_light, v_tss_none, v_venue_av, v_coord
        ]) AS u
    LOOP
        SELECT EXISTS (
            SELECT 1 FROM public.list_technical_support_candidates(v_req_probe)
            WHERE staff_id = r.staff_id
        ) INTO v_listed;
        EXECUTE 'SAVEPOINT probe';
        BEGIN
            PERFORM public.assign_technical_support_staff(
                v_event, v_req_probe, r.staff_id, v_coord);
            v_succeeded := TRUE;
        EXCEPTION WHEN OTHERS THEN
            v_succeeded := FALSE;
        END;
        EXECUTE 'ROLLBACK TO SAVEPOINT probe';
        IF v_listed <> v_succeeded THEN
            RAISE EXCEPTION 'AC3-X4: list says %, write says % for %',
                v_listed, v_succeeded, r.staff_id;
        END IF;
    END LOOP;
    SELECT count(*) INTO v_count
    FROM public.technical_support_assignments WHERE requirement_id = v_req_probe;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'AC3-X4: savepoint probes left % rows', v_count;
    END IF;

    -- AC5-X1b: notification retries dedupe on (recipient_id, event_id) — one
    -- notification row per assignment.
    INSERT INTO public.notifications (recipient_id, event_type, payload, event_id)
    VALUES (v_tss_av, 'technical_support_assigned',
            jsonb_build_object('event_request_id', v_event,
                               'requirement_id', v_req),
            v_assignment.id::text);
    BEGIN
        INSERT INTO public.notifications (recipient_id, event_type, payload, event_id)
        VALUES (v_tss_av, 'technical_support_assigned',
                jsonb_build_object('event_request_id', v_event,
                                   'requirement_id', v_req),
                v_assignment.id::text);
        RAISE EXCEPTION 'AC5-X1b: duplicate notification kept';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    SELECT count(*) INTO v_count
    FROM public.notifications
    WHERE recipient_id = v_tss_av AND event_id = v_assignment.id::text;
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'AC5-X1b: % notification rows', v_count;
    END IF;

    RAISE NOTICE 'ALL SCRUM-19 TECHNICAL SUPPORT VERIFICATIONS PASSED';
END
$verify$;

ROLLBACK;
