-- Run after 0016_venues.sql, 0018_venue_booking_requests.sql, 0041 and 0042; it also passes
-- on the full schema, where the slot cases follow 0050 (slots derived from times) and the
-- grant case follows 0056 (no direct INSERT).
-- Case IDs match docs/testcases/scrum_32_testcases.md (AC1 to AC6) and
-- docs/testcases/scrum_61_testcases.md (AC4-D1 to AC4-D8).
-- Every mutation is rolled back, so this leaves no venue or request data
-- behind. Before 0018 is applied it stops at the first statement that needs
-- the table, which is the intended Red result.
-- Needs no Supabase Auth user: requester and decider ids are random uuids,
-- because the actor columns carry no foreign key.

BEGIN;

CREATE TEMP TABLE verify_ctx ON COMMIT DROP AS
SELECT gen_random_uuid() AS event_id,
       gen_random_uuid() AS requester_id,
       gen_random_uuid() AS decider_id,
       NULL::uuid AS venue_id;

-- Inserts one request built from sensible defaults plus the given overrides.
-- An override of JSON null sets that column to NULL, so a case can remove a
-- required value. Returns the new id.
CREATE FUNCTION pg_temp.new_request(overrides jsonb DEFAULT '{}'::jsonb)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    ctx verify_ctx%ROWTYPE;
    doc jsonb;
    new_id uuid;
BEGIN
    SELECT * INTO ctx FROM verify_ctx;
    doc := jsonb_build_object(
        'id', gen_random_uuid(),
        'venue_id', ctx.venue_id,
        'requested_by', ctx.requester_id,
        'event_request_id', ctx.event_id,
        'event_name', 'Verify event',
        'expected_attendance', 40,
        'requirements_note', 'Projector',
        'start_date', '2030-01-10',
        'end_date', '2030-01-10',
        'slots', jsonb_build_array('AM'),
        'status', 'pending',
        'decision_reason', NULL,
        'suggested_alternative', NULL,
        'decided_by', NULL,
        'decided_at', NULL,
        'created_at', now()
    ) || overrides;

    INSERT INTO public.venue_booking_requests
    SELECT * FROM jsonb_populate_record(NULL::public.venue_booking_requests, doc)
    RETURNING id INTO new_id;

    RETURN new_id;
END;
$$;

-- Runs a statement and requires it to fail with exactly the expected SQLSTATE.
-- The failed statement is rolled back by its own sub-transaction.
CREATE FUNCTION pg_temp.expect_failure(
    case_id text,
    sql_text text,
    expected_state text
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    accepted boolean := false;
BEGIN
    BEGIN
        EXECUTE sql_text;
        accepted := true;
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLSTATE <> expected_state THEN
                RAISE EXCEPTION '% failed with SQLSTATE % (%), expected %',
                    case_id, SQLSTATE, SQLERRM, expected_state;
            END IF;
    END;

    IF accepted THEN
        RAISE EXCEPTION '% was accepted but should have been refused', case_id;
    END IF;
END;
$$;

CREATE FUNCTION pg_temp.expect_request_failure(
    case_id text,
    overrides jsonb,
    expected_state text
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_temp.expect_failure(
        case_id,
        format('SELECT pg_temp.new_request(%L::jsonb)', overrides::text),
        expected_state
    );
END;
$$;

DO $$
DECLARE
    ctx verify_ctx%ROWTYPE;
    v_venue uuid;
    v_id uuid;
    v_approved uuid;
    venue_before jsonb;
    row_count integer;
    slot_name text;
    role_name text;
    privilege_name text;
BEGIN
    -- A throwaway venue every case writes against.
    INSERT INTO public.venues (
        name, location, max_capacity, facilities, accessibility_features,
        supported_layouts, operating_slots
    )
    VALUES ('VERIFY venue', 'nowhere', 10, '{}', '{}', '{}', '{AM,PM,NIGHT}')
    RETURNING id INTO v_venue;

    UPDATE verify_ctx SET venue_id = v_venue;
    SELECT * INTO ctx FROM verify_ctx;
    SELECT to_jsonb(v) INTO venue_before FROM public.venues v WHERE v.id = v_venue;

    -- AC1-H1: status is omitted from the insert and defaults to pending.
    INSERT INTO public.venue_booking_requests (
        venue_id, requested_by, event_request_id, start_date, end_date, slots
    )
    VALUES (
        ctx.venue_id, ctx.requester_id, ctx.event_id,
        '2030-01-10', '2030-01-10', '{AM}'
    )
    RETURNING id INTO v_id;

    IF NOT EXISTS (
        SELECT 1 FROM public.venue_booking_requests
        WHERE id = v_id
          AND status = 'pending'
          AND created_at IS NOT NULL
          AND decided_by IS NULL
          AND decided_at IS NULL
          AND decision_reason IS NULL
          AND suggested_alternative IS NULL
    ) THEN
        RAISE EXCEPTION 'AC1-H1: a new request is not pending with empty decision fields';
    END IF;

    -- AC1-H2: a multi-day request with all three slots.
    PERFORM pg_temp.new_request(
        '{"start_date": "2030-01-10", "end_date": "2030-01-12",
          "slots": ["AM", "PM", "NIGHT"]}'
    );

    -- AC1-B1: the end date one day before the start is refused.
    PERFORM pg_temp.expect_request_failure(
        'AC1-B1',
        '{"start_date": "2030-01-10", "end_date": "2030-01-09"}',
        '23514'
    );

    -- AC1-B2: an end date equal to the start is accepted (inclusive).
    PERFORM pg_temp.new_request(
        '{"start_date": "2030-02-01", "end_date": "2030-02-01"}'
    );

    -- AC1-B3: an end date one day after the start is accepted.
    PERFORM pg_temp.new_request(
        '{"start_date": "2030-02-01", "end_date": "2030-02-02"}'
    );

    -- AC1-P1, AC1-P2, AC1-P3: each slot value alone is accepted.
    FOREACH slot_name IN ARRAY ARRAY['AM', 'PM', 'NIGHT'] LOOP
        PERFORM pg_temp.new_request(
            jsonb_build_object('slots', jsonb_build_array(slot_name))
        );
    END LOOP;

    -- AC1-N1: an empty slot list is refused. Since 0050 the slots convert to times
    -- on insert, and an empty list has no range to convert (22023).
    PERFORM pg_temp.expect_request_failure('AC1-N1', '{"slots": []}', '22023');

    -- AC1-N2, AC1-N3: since 0050 the stored slots are derived from the times, so a NULL
    -- or a duplicate in the slots sent on insert cannot be stored. It collapses to the
    -- slots the range touches; the time rules themselves are in
    -- verify_venue_booking_times.sql.
    v_id := pg_temp.new_request('{"slots": ["AM", null]}');
    IF (SELECT slots FROM public.venue_booking_requests WHERE id = v_id) <> '{AM}' THEN
        RAISE EXCEPTION 'AC1-N2: a NULL in the slots was stored';
    END IF;
    v_id := pg_temp.new_request('{"slots": ["AM", "AM"]}');
    IF (SELECT slots FROM public.venue_booking_requests WHERE id = v_id) <> '{AM}' THEN
        RAISE EXCEPTION 'AC1-N3: a duplicate slot was stored';
    END IF;

    -- AC1-N4: an unknown slot value is refused.
    PERFORM pg_temp.expect_request_failure(
        'AC1-N4', '{"slots": ["MORNING"]}', '22P02'
    );

    -- AC1-N5: a request for an unknown venue is refused.
    PERFORM pg_temp.expect_request_failure(
        'AC1-N5',
        jsonb_build_object('venue_id', gen_random_uuid()),
        '23503'
    );

    -- AC1-N6 to AC1-N10: each required column refuses NULL.
    PERFORM pg_temp.expect_request_failure(
        'AC1-N6', '{"requested_by": null}', '23502'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC1-N7', '{"event_request_id": null}', '23502'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC1-N8', '{"start_date": null}', '23502'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC1-N9', '{"end_date": null}', '23502'
    );
    -- With no slots and no times there is nothing to convert (22023, not 23502 since 0050).
    PERFORM pg_temp.expect_request_failure('AC1-N10', '{"slots": null}', '22023');

    -- AC1-X1: a venue that has requests cannot be deleted.
    PERFORM pg_temp.expect_failure(
        'AC1-X1',
        format('DELETE FROM public.venues WHERE id = %L', ctx.venue_id),
        '23503'
    );

    -- AC2-H1: the snapshot is stored exactly as given.
    v_id := pg_temp.new_request(
        '{"event_name": "Annual Gala", "expected_attendance": 120,
          "requirements_note": "Stage and projector"}'
    );
    IF NOT EXISTS (
        SELECT 1 FROM public.venue_booking_requests
        WHERE id = v_id
          AND event_name = 'Annual Gala'
          AND expected_attendance = 120
          AND requirements_note = 'Stage and projector'
    ) THEN
        RAISE EXCEPTION 'AC2-H1: the event snapshot was not stored as given';
    END IF;

    -- AC2-P1: a snapshot with no values is accepted.
    PERFORM pg_temp.new_request(
        '{"event_name": null, "expected_attendance": null,
          "requirements_note": null}'
    );

    -- AC3-H1: a pending request is in the pending queue; an approved one is not.
    v_id := pg_temp.new_request(
        '{"start_date": "2030-03-01", "end_date": "2030-03-01"}'
    );
    v_approved := pg_temp.new_request(
        jsonb_build_object(
            'start_date', '2030-03-01',
            'end_date', '2030-03-01',
            'status', 'approved',
            'decided_by', ctx.decider_id,
            'decided_at', now()
        )
    );
    IF NOT EXISTS (
        SELECT 1 FROM public.venue_booking_requests
        WHERE status = 'pending' AND id = v_id
    ) THEN
        RAISE EXCEPTION 'AC3-H1: a new request is missing from the pending queue';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.venue_booking_requests
        WHERE status = 'pending' AND id = v_approved
    ) THEN
        RAISE EXCEPTION 'AC3-H1: an approved request is in the pending queue';
    END IF;

    -- AC3-X1: the lookup indexes exist.
    SELECT count(*) INTO row_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'venue_booking_requests'
      AND indexname IN (
          'venue_booking_requests_venue_status_idx',
          'venue_booking_requests_requester_created_idx',
          'venue_booking_requests_pending_queue_idx',
          'venue_booking_requests_event_idx'
      );
    IF row_count <> 4 THEN
        RAISE EXCEPTION 'AC3-X1: expected 4 lookup indexes, found %', row_count;
    END IF;

    -- AC4-H1: two identical pending requests coexist.
    PERFORM pg_temp.new_request(
        '{"start_date": "2030-04-01", "end_date": "2030-04-01"}'
    );
    PERFORM pg_temp.new_request(
        '{"start_date": "2030-04-01", "end_date": "2030-04-01"}'
    );
    SELECT count(*) INTO row_count
    FROM public.venue_booking_requests
    WHERE venue_id = ctx.venue_id
      AND start_date = '2030-04-01'
      AND status = 'pending';
    IF row_count <> 2 THEN
        RAISE EXCEPTION 'AC4-H1: expected 2 coexisting pending requests, found %',
            row_count;
    END IF;

    -- AC5-P1: an approved request with a decider and a time is accepted.
    PERFORM pg_temp.new_request(
        jsonb_build_object(
            'status', 'approved',
            'decided_by', ctx.decider_id,
            'decided_at', now()
        )
    );

    -- AC5-P2: a rejected request with a reason and no alternative is accepted.
    PERFORM pg_temp.new_request(
        jsonb_build_object(
            'status', 'rejected',
            'decided_by', ctx.decider_id,
            'decided_at', now(),
            'decision_reason', 'Not available that day'
        )
    );

    -- AC5-P3: a rejected request with a reason and an alternative is accepted.
    PERFORM pg_temp.new_request(
        jsonb_build_object(
            'status', 'rejected',
            'decided_by', ctx.decider_id,
            'decided_at', now(),
            'decision_reason', 'Not available that day',
            'suggested_alternative', 'Level 3 hall on the following day'
        )
    );

    -- AC5-N1 to AC5-N4: a pending request with any decision field is refused.
    PERFORM pg_temp.expect_request_failure(
        'AC5-N1', jsonb_build_object('decided_by', ctx.decider_id), '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC5-N2', jsonb_build_object('decided_at', now()), '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC5-N3', '{"decision_reason": "No"}', '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC5-N4', '{"suggested_alternative": "Elsewhere"}', '23514'
    );

    -- AC5-N5, AC5-N6: an approved request needs both a decider and a time.
    PERFORM pg_temp.expect_request_failure(
        'AC5-N5',
        jsonb_build_object('status', 'approved', 'decided_at', now()),
        '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC5-N6',
        jsonb_build_object('status', 'approved', 'decided_by', ctx.decider_id),
        '23514'
    );

    -- AC5-N7, AC5-N8: an approved request carries no reason or alternative.
    PERFORM pg_temp.expect_request_failure(
        'AC5-N7',
        jsonb_build_object(
            'status', 'approved',
            'decided_by', ctx.decider_id,
            'decided_at', now(),
            'decision_reason', 'No'
        ),
        '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC5-N8',
        jsonb_build_object(
            'status', 'approved',
            'decided_by', ctx.decider_id,
            'decided_at', now(),
            'suggested_alternative', 'Elsewhere'
        ),
        '23514'
    );

    -- AC5-N9, AC5-N10: a rejected request needs a non-blank reason.
    PERFORM pg_temp.expect_request_failure(
        'AC5-N9',
        jsonb_build_object(
            'status', 'rejected',
            'decided_by', ctx.decider_id,
            'decided_at', now()
        ),
        '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC5-N10',
        jsonb_build_object(
            'status', 'rejected',
            'decided_by', ctx.decider_id,
            'decided_at', now(),
            'decision_reason', '   '
        ),
        '23514'
    );

    -- AC5-N11, AC5-N12: a rejected request needs a decider and a time.
    PERFORM pg_temp.expect_request_failure(
        'AC5-N11',
        jsonb_build_object(
            'status', 'rejected',
            'decided_at', now(),
            'decision_reason', 'Not available'
        ),
        '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC5-N12',
        jsonb_build_object(
            'status', 'rejected',
            'decided_by', ctx.decider_id,
            'decision_reason', 'Not available'
        ),
        '23514'
    );

    -- AC5-N13: an unknown status value is refused. ('cancelled' became a real
    -- status in 0041, so another unknown value is used.)
    PERFORM pg_temp.expect_request_failure(
        'AC5-N13', '{"status": "archived"}', '22P02'
    );

    -- AC4-D1, AC4-D2: a cancelled request needs both cancelled_by and cancelled_at.
    PERFORM pg_temp.expect_request_failure(
        'AC4-D1',
        jsonb_build_object('status', 'cancelled', 'cancelled_at', now()),
        '23514'
    );
    PERFORM pg_temp.expect_request_failure(
        'AC4-D2',
        jsonb_build_object('status', 'cancelled', 'cancelled_by', ctx.decider_id),
        '23514'
    );

    -- AC4-D3: only a cancelled request may carry cancelled_by and cancelled_at.
    PERFORM pg_temp.expect_request_failure(
        'AC4-D3',
        jsonb_build_object(
            'cancelled_by', ctx.decider_id, 'cancelled_at', now()
        ),
        '23514'
    );

    -- AC4-D4: a cancelled request carries no decision reason.
    PERFORM pg_temp.expect_request_failure(
        'AC4-D4',
        jsonb_build_object(
            'status', 'cancelled',
            'cancelled_by', ctx.decider_id,
            'cancelled_at', now(),
            'decision_reason', 'Because'
        ),
        '23514'
    );

    -- AC4-D5: a request cancelled before any decision, and one cancelled after
    -- approval (decider and time kept), are both accepted.
    PERFORM pg_temp.new_request(jsonb_build_object(
        'status', 'cancelled',
        'cancelled_by', ctx.decider_id,
        'cancelled_at', now()
    ));
    PERFORM pg_temp.new_request(jsonb_build_object(
        'status', 'cancelled',
        'cancelled_by', ctx.decider_id,
        'cancelled_at', now(),
        'decided_by', ctx.decider_id,
        'decided_at', now()
    ));

    -- AC4-D6: the function cancels a pending request and records who and when.
    v_id := pg_temp.new_request();
    PERFORM public.cancel_venue_booking_request(v_id, ctx.decider_id);
    IF NOT EXISTS (
        SELECT 1 FROM public.venue_booking_requests r
        WHERE r.id = v_id AND r.status = 'cancelled'
          AND r.cancelled_by = ctx.decider_id AND r.cancelled_at IS NOT NULL
          AND r.decided_by IS NULL
    ) THEN
        RAISE EXCEPTION 'AC4-D6: a pending request was not cancelled correctly';
    END IF;

    -- AC4-D7: the function cancels an approved request and keeps its decision.
    v_approved := pg_temp.new_request(jsonb_build_object(
        'status', 'approved',
        'decided_by', ctx.decider_id,
        'decided_at', now()
    ));
    PERFORM public.cancel_venue_booking_request(v_approved, ctx.requester_id);
    IF NOT EXISTS (
        SELECT 1 FROM public.venue_booking_requests r
        WHERE r.id = v_approved AND r.status = 'cancelled'
          AND r.cancelled_by = ctx.requester_id
          AND r.decided_by = ctx.decider_id
    ) THEN
        RAISE EXCEPTION 'AC4-D7: an approved request was not cancelled correctly';
    END IF;

    -- AC4-D8: the function refuses a rejected or already cancelled request, an
    -- unknown request and a missing user, and is closed to browser roles.
    v_id := pg_temp.new_request(jsonb_build_object(
        'status', 'rejected',
        'decided_by', ctx.decider_id,
        'decided_at', now(),
        'decision_reason', 'Not available'
    ));
    PERFORM pg_temp.expect_failure(
        'AC4-D8 rejected',
        format('SELECT public.cancel_venue_booking_request(%L, %L)', v_id, ctx.decider_id),
        '55000'
    );
    PERFORM pg_temp.expect_failure(
        'AC4-D8 already cancelled',
        format('SELECT public.cancel_venue_booking_request(%L, %L)', v_approved, ctx.decider_id),
        '55000'
    );
    PERFORM pg_temp.expect_failure(
        'AC4-D8 unknown',
        format('SELECT public.cancel_venue_booking_request(%L, %L)', gen_random_uuid(), ctx.decider_id),
        'P0002'
    );
    PERFORM pg_temp.expect_failure(
        'AC4-D8 no user',
        format('SELECT public.cancel_venue_booking_request(%L, NULL)', v_id),
        '22023'
    );
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF has_function_privilege(
            role_name, 'public.cancel_venue_booking_request(uuid, uuid)', 'EXECUTE'
        ) THEN
            RAISE EXCEPTION 'AC4-D8: % can execute cancel_venue_booking_request', role_name;
        END IF;
    END LOOP;
    IF NOT has_function_privilege(
        'service_role', 'public.cancel_venue_booking_request(uuid, uuid)', 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'AC4-D8: service_role cannot execute cancel_venue_booking_request';
    END IF;

    -- AC4-X1: none of the above changed the venue row.
    IF (SELECT to_jsonb(v) FROM public.venues v WHERE v.id = ctx.venue_id)
        IS DISTINCT FROM venue_before
    THEN
        RAISE EXCEPTION 'AC4-X1: submitting requests changed the venue row';
    END IF;

    -- AC6-X1: browser roles have no direct privilege on the table.
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        FOREACH privilege_name IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
            IF has_table_privilege(
                role_name, 'public.venue_booking_requests', privilege_name
            ) THEN
                RAISE EXCEPTION 'AC6-X1: % holds % on venue_booking_requests',
                    role_name, privilege_name;
            END IF;
        END LOOP;
    END LOOP;

    -- AC6-X2: row-level security is enabled.
    IF NOT (
        SELECT relrowsecurity FROM pg_class
        WHERE oid = 'public.venue_booking_requests'::regclass
    ) THEN
        RAISE EXCEPTION 'AC6-X2: row-level security is not enabled';
    END IF;

    -- AC6-X3: the service role can read and update. Since 0056 it cannot INSERT or DELETE
    -- directly; a request is created only by create_event_venue_booking_request, which
    -- checks the event's version (verified in verify_versioned_venue_booking_creation.sql).
    FOREACH privilege_name IN ARRAY ARRAY['SELECT', 'UPDATE'] LOOP
        IF NOT has_table_privilege(
            'service_role', 'public.venue_booking_requests', privilege_name
        ) THEN
            RAISE EXCEPTION 'AC6-X3: service_role lacks % on venue_booking_requests',
                privilege_name;
        END IF;
    END LOOP;
    FOREACH privilege_name IN ARRAY ARRAY['INSERT', 'DELETE'] LOOP
        IF has_table_privilege(
            'service_role', 'public.venue_booking_requests', privilege_name
        ) THEN
            RAISE EXCEPTION 'AC6-X3: service_role holds % on venue_booking_requests',
                privilege_name;
        END IF;
    END LOOP;

    RAISE NOTICE 'ALL VENUE BOOKING REQUEST VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
