-- Behavioural verification for reserving equipment (SCRUM-13).
--
-- Run in the Supabase SQL Editor AFTER applying migrations 0027 (the
-- requirement_id column and the reserve_equipment function) and 0028 (the
-- type check inside reserve_equipment, D12). Before 0027 it fails with
-- "column requirement_id does not exist" or "function reserve_equipment does
-- not exist"; before 0028 it stops at the AC1-N10 line. Both are the
-- expected Red. The whole
-- script runs in one transaction and ROLLBACKs, so it never leaves data
-- behind; pass/fail is the final NOTICE or the first error message.
--
-- Test-case IDs trace to docs/testcases/scrum_13_testcases.md.
-- Needs at least one row in auth.users (run seed_test_accounts.sql first).
--
-- Contract under test (decisions D5 to D7, D12):
--   reserve_equipment(p_requirement_id uuid, p_equipment_id uuid,
--                     p_quantity integer, p_collection_date date,
--                     p_return_date date, p_created_by uuid)
--     RETURNS equipment_reservations
--   Locks the requirement then the equipment row, checks the row's type
--   matches the requirement's (trimmed, whitespace collapsed, case ignored),
--   re-checks its status, the requirement's outstanding quantity and the
--   units already held on the busiest day of [p_collection_date,
--   p_return_date], then inserts. event_request_id is copied from the
--   requirement. P0002 = not found, P0004 = refused, 22023 = type mismatch.
--
-- AC3-N2 (two staff racing for the last units) needs two SQL sessions and
-- is described at the end of this file; it is not part of the DO block.

BEGIN;

DO $$
DECLARE
    v_user uuid;
    v_staff uuid := '00000000-0000-0000-0000-000000000000';
    v_missing uuid := '11111111-1111-1111-1111-111111111111';
    v_equipment uuid;
    v_damaged uuid;
    v_speaker uuid;
    v_spaced uuid;
    v_event uuid;
    v_requirement uuid;
    v_big_requirement uuid;
    v_row public.equipment_reservations;
    v_count integer;
BEGIN
    SELECT id INTO v_user FROM auth.users LIMIT 1;
    IF v_user IS NULL THEN
        RAISE EXCEPTION 'verify: needs at least one auth.users row (run seed_test_accounts.sql)';
    END IF;

    INSERT INTO equipment (type, total_owned_quantity, home_location, created_by)
    VALUES ('VERIFY-13 Projector', 10, 'Store Room B', v_staff)
    RETURNING id INTO v_equipment;

    INSERT INTO equipment (type, total_owned_quantity, home_location, created_by)
    VALUES ('VERIFY-13 Projector', 10, 'Store Room C', v_staff)
    RETURNING id INTO v_damaged;

    INSERT INTO event_requests (organiser_id, event_name)
    VALUES (v_user, 'VERIFY SCRUM-13 event')
    RETURNING id INTO v_event;

    INSERT INTO equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
    VALUES (v_event, 'VERIFY-13 Projector', 5, v_user)
    RETURNING id INTO v_requirement;

    INSERT INTO equipment_requirements (event_request_id, equipment_type, quantity, recorded_by)
    VALUES (v_event, 'VERIFY-13 Projector', 20, v_user)
    RETURNING id INTO v_big_requirement;

    -- AC4-H2 (happy): the function stores every column and takes the event from the requirement
    SELECT * INTO v_row FROM public.reserve_equipment(
        v_requirement, v_equipment, 2, DATE '2026-10-13', DATE '2026-10-14', v_staff
    );
    ASSERT v_row.id IS NOT NULL, 'AC4-H2: a reservation id should be returned';
    ASSERT v_row.requirement_id = v_requirement, 'AC4-H2: requirement_id stored';
    ASSERT v_row.event_request_id = v_event, 'AC4-H2: event copied from the requirement';
    ASSERT v_row.equipment_id = v_equipment, 'AC4-H2: equipment_id stored';
    ASSERT v_row.quantity = 2, 'AC4-H2: quantity stored';
    ASSERT v_row.collection_date = DATE '2026-10-13', 'AC4-H2: collection_date stored';
    ASSERT v_row.return_date = DATE '2026-10-14', 'AC4-H2: return_date stored';
    ASSERT v_row.created_by = v_staff, 'AC4-H2: created_by stored';
    ASSERT v_row.created_at IS NOT NULL, 'AC4-H2: created_at set';

    -- AC1-N9 (negative): a reservation must name a real requirement ...
    BEGIN
        INSERT INTO equipment_reservations
            (requirement_id, equipment_id, event_request_id, quantity,
             collection_date, return_date, created_by)
        VALUES (v_missing, v_equipment, v_event, 1,
                DATE '2026-10-13', DATE '2026-10-14', v_staff);
        RAISE EXCEPTION 'AC1-N9: unknown requirement_id should violate the foreign key';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;  -- expected
    END;

    -- AC1-N9 (negative): ... and cannot omit it
    BEGIN
        INSERT INTO equipment_reservations
            (requirement_id, equipment_id, event_request_id, quantity,
             collection_date, return_date, created_by)
        VALUES (NULL, v_equipment, v_event, 1,
                DATE '2026-10-13', DATE '2026-10-14', v_staff);
        RAISE EXCEPTION 'AC1-N9: NULL requirement_id should violate NOT NULL';
    EXCEPTION
        WHEN not_null_violation THEN NULL;  -- expected
    END;

    -- AC2-N2 (negative): a non-AVAILABLE row is refused under the lock
    UPDATE equipment SET operational_status = 'DAMAGED' WHERE id = v_damaged;
    BEGIN
        PERFORM public.reserve_equipment(
            v_big_requirement, v_damaged, 1, DATE '2026-10-13', DATE '2026-10-14', v_staff
        );
        RAISE EXCEPTION 'AC2-N2: a DAMAGED row should be refused';
    EXCEPTION
        WHEN SQLSTATE 'P0004' THEN NULL;  -- expected
    END;
    SELECT count(*) INTO v_count FROM equipment_reservations WHERE equipment_id = v_damaged;
    ASSERT v_count = 0, 'AC2-N2: nothing stored for the DAMAGED row';

    -- AC1-N10 (negative): Speaker stock against a Projector requirement is refused under the lock
    INSERT INTO equipment (type, total_owned_quantity, home_location, created_by)
    VALUES ('VERIFY-13 Speaker', 10, 'Store Room B', v_staff)
    RETURNING id INTO v_speaker;
    BEGIN
        PERFORM public.reserve_equipment(
            v_requirement, v_speaker, 1, DATE '2026-10-13', DATE '2026-10-14', v_staff
        );
        RAISE EXCEPTION 'AC1-N10: a Speaker row must not be reserved against a Projector requirement';
    EXCEPTION
        WHEN SQLSTATE '22023' THEN NULL;  -- expected
    END;
    SELECT count(*) INTO v_count FROM equipment_reservations WHERE equipment_id = v_speaker;
    ASSERT v_count = 0, 'AC1-N10: nothing stored for the mismatched row';

    -- AC1-N11 (partition): a type differing only by case and spacing is the same type.
    -- v_requirement needs 5 and holds 2 (AC4-H2), so 1 more is within D3.
    INSERT INTO equipment (type, total_owned_quantity, home_location, created_by)
    VALUES ('  verify-13   PROJECTOR ', 10, 'Store Room B', v_staff)
    RETURNING id INTO v_spaced;
    SELECT * INTO v_row FROM public.reserve_equipment(
        v_requirement, v_spaced, 1, DATE '2026-10-13', DATE '2026-10-14', v_staff
    );
    ASSERT v_row.equipment_id = v_spaced, 'AC1-N11: normalised type match accepted';

    -- AC3-N1 (negative): the function re-checks the units held in the window.
    -- v_equipment already holds 2 (AC4-H2); add 6 more, leaving 2 free.
    PERFORM public.reserve_equipment(
        v_big_requirement, v_equipment, 6, DATE '2026-10-13', DATE '2026-10-14', v_staff
    );
    BEGIN
        PERFORM public.reserve_equipment(
            v_big_requirement, v_equipment, 5, DATE '2026-10-12', DATE '2026-10-13', v_staff
        );
        RAISE EXCEPTION 'AC3-N1: 5 units should be refused when only 2 are free';
    EXCEPTION
        WHEN SQLSTATE 'P0004' THEN NULL;  -- expected
    END;
    SELECT coalesce(sum(quantity), 0) INTO v_count
        FROM equipment_reservations WHERE equipment_id = v_equipment;
    ASSERT v_count = 8, 'AC3-N1: the refused call must not add units';

    RAISE NOTICE 'ALL EQUIPMENT RESERVATION WRITE VERIFICATIONS PASSED';
END $$;

ROLLBACK;

-- AC3-N2 (negative): two staff reserving the last units at once.
--
-- Needs two SQL sessions on the same database (two SQL Editor tabs do not
-- share a transaction, so use psql or two connections). Prepare one
-- 10-unit AVAILABLE row and one requirement of quantity 10, then:
--
--   Session 1: BEGIN;
--              SELECT * FROM reserve_equipment(<req>, <row>, 6,
--                  '2026-10-13', '2026-10-14', <staff>);
--   Session 2: SELECT * FROM reserve_equipment(<req>, <row>, 6,
--                  '2026-10-13', '2026-10-14', <staff>);
--              -- waits on the row lock
--   Session 1: COMMIT;
--
-- Expected: session 1 returns the row; session 2 then fails with SQLSTATE
-- P0004; SELECT sum(quantity) for the row is 6. Delete the test rows after.
