-- Run after 0016_venues.sql, 0018_venue_booking_requests.sql,
-- 0023_venue_blocks.sql and 0024_venue_booking_decisions.sql, and since SCRUM-65
-- after 0050 and 0051 (blocks take times; operating slots no longer refuse).
-- Case IDs match docs/testcases/scrum_15_testcases.md (DB-1, DB-2).
-- Every mutation is rolled back, so this leaves no venue, block, request or
-- refusal data behind. Before 0024 is applied it stops at the first call to
-- decide_venue_booking_request, which is the intended Red result.
-- Borrows the oldest auth user as staff: on shared, venue_blocks.created_by has a
-- foreign key to auth.users (venue_blocks_created_by_fkey, not in the migrations),
-- so DB-2's block needs a real user. The requester and event ids stay random.

BEGIN;

CREATE TEMP TABLE verify_ctx ON COMMIT DROP AS
SELECT (SELECT id FROM auth.users ORDER BY created_at LIMIT 1) AS staff_id,
       gen_random_uuid() AS requester_id,
       gen_random_uuid() AS event_id;

CREATE FUNCTION pg_temp.new_venue(
    operating public.booking_slot[] DEFAULT ARRAY['AM', 'PM']::public.booking_slot[],
    venue_status public.venue_status DEFAULT 'available'
)
RETURNS uuid
LANGUAGE sql
AS $$
    INSERT INTO public.venues (
        name, location, max_capacity, facilities, accessibility_features,
        supported_layouts, operating_slots, status
    )
    VALUES ('Verify hall', 'Verify', 50, '{}', '{}', '{}', operating, venue_status)
    RETURNING id;
$$;

CREATE FUNCTION pg_temp.new_request(
    venue uuid, first_day date, last_day date, wanted public.booking_slot[]
)
RETURNS uuid
LANGUAGE sql
AS $$
    INSERT INTO public.venue_booking_requests (
        venue_id, requested_by, event_request_id, start_date, end_date, slots
    )
    SELECT venue, requester_id, event_id, first_day, last_day, wanted FROM verify_ctx
    RETURNING id;
$$;

CREATE FUNCTION pg_temp.decide(
    request uuid, decision text, reason text DEFAULT NULL, alternative text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE sql
AS $$
    SELECT public.decide_venue_booking_request(request, decision, staff_id, reason, alternative)
    FROM verify_ctx;
$$;

-- Requires a statement to fail with exactly the expected SQLSTATE.
CREATE FUNCTION pg_temp.expect_failure(case_id text, statement text, expected text)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    EXECUTE statement;
    RAISE EXCEPTION '%: expected SQLSTATE % but the statement succeeded', case_id, expected;
EXCEPTION
    WHEN OTHERS THEN
        IF SQLSTATE <> expected THEN
            RAISE EXCEPTION '%: expected SQLSTATE % but got % (%)',
                case_id, expected, SQLSTATE, SQLERRM;
        END IF;
END;
$$;

DO $$
DECLARE
    venue uuid := pg_temp.new_venue();
    other_venue uuid := pg_temp.new_venue();
    first_request uuid;
    second_request uuid;
    request uuid;
    result jsonb;
    block uuid;
    refusal public.venue_booking_refusals%ROWTYPE;
    staff uuid := (SELECT staff_id FROM verify_ctx);
BEGIN
    -- AC1-H1: approving a free slot books it.
    first_request := pg_temp.new_request(venue, '2030-01-20', '2030-01-21', '{AM}');
    result := pg_temp.decide(first_request, 'approved');
    IF result ->> 'outcome' <> 'approved'
       OR (SELECT status FROM public.venue_booking_requests WHERE id = first_request) <> 'approved'
       OR (SELECT decided_by FROM public.venue_booking_requests WHERE id = first_request) <> staff THEN
        RAISE EXCEPTION 'AC1-H1: approval not saved: %', result;
    END IF;

    -- AC1-N1: a decided request cannot be decided again.
    PERFORM pg_temp.expect_failure(
        'AC1-N1', format('SELECT pg_temp.decide(%L, %L, %L)', first_request, 'rejected', 'late'), '55000'
    );

    -- AC1-N2: an unknown request.
    PERFORM pg_temp.expect_failure(
        'AC1-N2', format('SELECT pg_temp.decide(%L, %L)', gen_random_uuid(), 'approved'), 'P0002'
    );

    -- AC2-N1 / AC2-N2: invalid decisions change nothing.
    request := pg_temp.new_request(venue, '2030-02-01', '2030-02-01', '{AM}');
    PERFORM pg_temp.expect_failure(
        'AC2-N1', format('SELECT pg_temp.decide(%L, %L, %L)', request, 'rejected', '   '), '22023'
    );
    PERFORM pg_temp.expect_failure(
        'AC2-N2', format('SELECT pg_temp.decide(%L, %L, %L)', request, 'approved', 'ok'), '22023'
    );
    IF (SELECT status FROM public.venue_booking_requests WHERE id = request) <> 'pending' THEN
        RAISE EXCEPTION 'AC2-N1/N2: a refused decision changed the request';
    END IF;

    -- AC1-H2: rejecting records a trimmed reason and an alternative.
    result := pg_temp.decide(request, 'rejected', ' Hall under repair ', ' Try Orchard ');
    IF (SELECT decision_reason FROM public.venue_booking_requests WHERE id = request) <> 'Hall under repair'
       OR (SELECT suggested_alternative FROM public.venue_booking_requests WHERE id = request) <> 'Try Orchard' THEN
        RAISE EXCEPTION 'AC1-H2: rejection details not saved: %', result;
    END IF;

    -- AC6-H1 / AC6-B1: an approved overlapping booking refuses approval, inclusively.
    second_request := pg_temp.new_request(venue, '2030-01-21', '2030-01-22', '{AM}');
    result := pg_temp.decide(second_request, 'approved');
    IF result ->> 'outcome' <> 'refused'
       OR NOT (result -> 'refusal_codes') ? 'booking_conflict'
       OR NOT (result -> 'conflicting_booking_ids') ? first_request::text
       OR (SELECT status FROM public.venue_booking_requests WHERE id = second_request) <> 'pending' THEN
        RAISE EXCEPTION 'AC6-H1: conflict not refused: %', result;
    END IF;
    SELECT * INTO refusal FROM public.venue_booking_refusals WHERE booking_request_id = second_request;
    IF refusal.refused_by <> staff OR refusal.refusal_codes <> ARRAY['booking_conflict'] THEN
        RAISE EXCEPTION 'AC6-H1: refusal not recorded';
    END IF;

    -- AC6-B1: the day after the booking ends is free.
    request := pg_temp.new_request(venue, '2030-01-22', '2030-01-23', '{AM}');
    IF pg_temp.decide(request, 'approved') ->> 'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC6-B1: the day after an approved booking was refused';
    END IF;

    -- AC6-P1 / AC6-P2: pending and rejected requests, other venues and other slots never conflict.
    PERFORM pg_temp.new_request(venue, '2030-03-01', '2030-03-01', '{AM}');
    request := pg_temp.new_request(other_venue, '2030-01-20', '2030-01-20', '{AM}');
    IF pg_temp.decide(request, 'approved') ->> 'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC6-P2: another venue''s booking conflicted';
    END IF;
    request := pg_temp.new_request(venue, '2030-01-20', '2030-01-20', '{PM}');
    IF pg_temp.decide(request, 'approved') ->> 'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC6-P2: a different slot conflicted';
    END IF;
    request := pg_temp.new_request(venue, '2030-03-01', '2030-03-01', '{AM}');
    IF pg_temp.decide(request, 'approved') ->> 'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC6-P1: a pending request conflicted';
    END IF;

    -- DB-2 / AC5-H1: a block created under the venue lock refuses approval and is recorded.
    SELECT id INTO block FROM public.create_venue_block(
        venue, '2030-04-02', '2030-04-02', 420, 720, 'maintenance', '  Repairs  ', staff
    );
    IF (SELECT reason_detail FROM public.venue_blocks WHERE id = block) <> 'Repairs' THEN
        RAISE EXCEPTION 'DB-2: block detail not trimmed';
    END IF;
    request := pg_temp.new_request(venue, '2030-04-01', '2030-04-02', '{AM}');
    result := pg_temp.decide(request, 'approved');
    IF result ->> 'outcome' <> 'refused'
       OR NOT (result -> 'refusal_codes') ? 'active_block'
       OR NOT (result -> 'conflicting_block_ids') ? block::text THEN
        RAISE EXCEPTION 'AC5-H1: block did not refuse approval: %', result;
    END IF;
    PERFORM pg_temp.expect_failure(
        'DB-2',
        format(
            'SELECT public.create_venue_block(%L, %L, %L, 420, 720, %L, NULL, %L)',
            gen_random_uuid(), '2030-04-02', '2030-04-02', 'maintenance', staff
        ),
        'P0002'
    );

    -- AC5-P3: a lifted block does not refuse.
    UPDATE public.venue_blocks SET status = 'lifted' WHERE id = block;
    IF pg_temp.decide(request, 'approved') ->> 'outcome' <> 'approved' THEN
        RAISE EXCEPTION 'AC5-P3: a lifted block refused approval';
    END IF;

    -- AC5-P1 / AC5-P2: a catalogue-blocked venue and a non-operating slot refuse.
    request := pg_temp.new_request(
        pg_temp.new_venue(venue_status => 'blocked'), '2030-05-01', '2030-05-01', '{NIGHT}'
    );
    result := pg_temp.decide(request, 'approved');
    -- SCRUM-65 (0051): the operating-slot refusal is retired.
    IF result -> 'refusal_codes' <> '["venue_unavailable"]'::jsonb THEN
        RAISE EXCEPTION 'AC5-P1/P2: wrong refusal codes: %', result;
    END IF;

    -- DB-1: browser roles cannot execute the functions or read the refusal log.
    IF has_function_privilege(
           'anon', 'public.decide_venue_booking_request(uuid, text, uuid, text, text)', 'EXECUTE')
       OR has_function_privilege(
           'authenticated', 'public.decide_venue_booking_request(uuid, text, uuid, text, text)', 'EXECUTE')
       OR has_function_privilege(
           'anon',
           'public.create_venue_block(uuid, date, date, integer, integer, public.block_reason, text, uuid)',
           'EXECUTE')
       OR has_table_privilege('anon', 'public.venue_booking_refusals', 'SELECT')
       OR has_table_privilege('authenticated', 'public.venue_booking_refusals', 'SELECT') THEN
        RAISE EXCEPTION 'DB-1: a browser role can reach the decision functions or refusal log';
    END IF;
    IF NOT has_function_privilege(
           'service_role', 'public.decide_venue_booking_request(uuid, text, uuid, text, text)', 'EXECUTE') THEN
        RAISE EXCEPTION 'DB-1: service_role cannot execute decide_venue_booking_request';
    END IF;

    RAISE NOTICE 'ALL VENUE BOOKING DECISION VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
