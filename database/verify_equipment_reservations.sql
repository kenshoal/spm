-- Behavioural verification for the equipment_reservations table (SCRUM-10).
--
-- Run in the Supabase SQL Editor AFTER applying migration 0020. Before the
-- migration it fails with "relation equipment_reservations does not exist",
-- which is the expected Red. The whole script runs in one transaction and
-- ROLLBACKs, so it never leaves data behind; pass/fail is the final NOTICE
-- or the first error message.
--
-- Test-case IDs trace to docs/testcases/scrum_10_testcases.md.
-- Needs at least one row in auth.users (run seed_test_accounts.sql first).
--
-- Not covered here: AC3-X2 (browser roles cannot read or write the table).
-- That needs the publishable key via the REST API, as for the other
-- equipment tables; see the equipmentService README.

BEGIN;

DO $$
DECLARE
    v_user uuid;
    v_staff uuid := '00000000-0000-0000-0000-000000000000';
    v_missing uuid := '11111111-1111-1111-1111-111111111111';
    v_equipment uuid;
    v_event uuid;
    v_count integer;
BEGIN
    SELECT id INTO v_user FROM auth.users LIMIT 1;
    IF v_user IS NULL THEN
        RAISE EXCEPTION 'verify: needs at least one auth.users row (run seed_test_accounts.sql)';
    END IF;

    INSERT INTO equipment (type, total_owned_quantity, home_location, created_by)
    VALUES ('VERIFY-Projector', 10, 'Store Room B', v_staff)
    RETURNING id INTO v_equipment;

    INSERT INTO event_requests (organiser_id, event_name)
    VALUES (v_user, 'VERIFY SCRUM-10 event')
    RETURNING id INTO v_event;

    -- AC3-H4 (happy): a valid reservation row can be stored
    INSERT INTO equipment_reservations
        (equipment_id, event_request_id, quantity, collection_date, return_date, created_by)
    VALUES (v_equipment, v_event, 2, DATE '2026-10-11', DATE '2026-10-12', v_staff);
    SELECT count(*) INTO v_count FROM equipment_reservations
        WHERE equipment_id = v_equipment;
    ASSERT v_count = 1, 'AC3-H4: the valid reservation should be stored';

    -- AC3-N2 (negative, accepted side): a same-day hold is allowed
    INSERT INTO equipment_reservations
        (equipment_id, event_request_id, quantity, collection_date, return_date, created_by)
    VALUES (v_equipment, v_event, 1, DATE '2026-10-12', DATE '2026-10-12', v_staff);

    -- AC3-N1 (negative): quantity must be positive
    BEGIN
        INSERT INTO equipment_reservations
            (equipment_id, event_request_id, quantity, collection_date, return_date, created_by)
        VALUES (v_equipment, v_event, 0, DATE '2026-10-11', DATE '2026-10-12', v_staff);
        RAISE EXCEPTION 'AC3-N1: quantity 0 should violate the CHECK constraint';
    EXCEPTION
        WHEN check_violation THEN NULL;  -- expected
    END;

    -- AC3-N2 (negative): return date cannot be before collection date
    BEGIN
        INSERT INTO equipment_reservations
            (equipment_id, event_request_id, quantity, collection_date, return_date, created_by)
        VALUES (v_equipment, v_event, 1, DATE '2026-10-12', DATE '2026-10-11', v_staff);
        RAISE EXCEPTION 'AC3-N2: return before collection should violate the CHECK constraint';
    EXCEPTION
        WHEN check_violation THEN NULL;  -- expected
    END;

    -- AC3-N3 (negative): the reservation must point at real equipment ...
    BEGIN
        INSERT INTO equipment_reservations
            (equipment_id, event_request_id, quantity, collection_date, return_date, created_by)
        VALUES (v_missing, v_event, 1, DATE '2026-10-11', DATE '2026-10-12', v_staff);
        RAISE EXCEPTION 'AC3-N3: unknown equipment_id should violate the foreign key';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;  -- expected
    END;

    -- AC3-N3 (negative): ... and a real event request
    BEGIN
        INSERT INTO equipment_reservations
            (equipment_id, event_request_id, quantity, collection_date, return_date, created_by)
        VALUES (v_equipment, v_missing, 1, DATE '2026-10-11', DATE '2026-10-12', v_staff);
        RAISE EXCEPTION 'AC3-N3: unknown event_request_id should violate the foreign key';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;  -- expected
    END;

    SELECT count(*) INTO v_count FROM equipment_reservations
        WHERE equipment_id = v_equipment;
    ASSERT v_count = 2, 'refused inserts must not leave rows behind';

    RAISE NOTICE 'ALL EQUIPMENT RESERVATION VERIFICATIONS PASSED';
END $$;

ROLLBACK;
