-- Behavioural verification for the equipment SQL functions.
--
-- Run in the Supabase SQL Editor AFTER applying migrations 0001-0005.
-- Exercises the real functions (not the API layer): atomic create, status
-- transition history, the P0002 not-found contract, quantity audit logging,
-- and the quantity CHECK constraint. The whole script runs in one
-- transaction and ROLLBACKs, so it never leaves data behind — pass/fail is
-- the final NOTICE / error message.
--
-- Not covered here: RLS behaviour (needs the anon/publishable key via the
-- REST API — see the README) and the service-role bypass, which this
-- editor session does not run as.

BEGIN;

DO $$
DECLARE
    v equipment;
    h equipment_status_history;
    q equipment_quantity_history;
    v_staff uuid := '00000000-0000-0000-0000-000000000000';
    v_missing uuid := '11111111-1111-1111-1111-111111111111';
BEGIN
    -- 1. create_equipment: the row and its first history entry land together
    v := create_equipment(
        p_type => 'VERIFY-Speaker',
        p_description => 'verification row',
        p_total_owned_quantity => 4,
        p_home_location => 'Store Room B',
        p_created_by => v_staff
    );
    SELECT * INTO h FROM equipment_status_history WHERE equipment_id = v.id;
    ASSERT h.old_status IS NULL, 'create: first history row should have old_status NULL';
    ASSERT h.new_status = 'AVAILABLE', 'create: first history row should record AVAILABLE';
    ASSERT v.total_owned_quantity = 4, 'create: returned row should carry the quantity';

    -- 2. transition_equipment_status: updates the row and appends history
    PERFORM transition_equipment_status(
        p_equipment_id => v.id,
        p_new_status => 'DAMAGED',
        p_changed_by => v_staff,
        p_reason => 'verify'
    );
    SELECT * INTO h
    FROM equipment_status_history
    WHERE equipment_id = v.id
    ORDER BY id DESC
    LIMIT 1;
    ASSERT h.old_status = 'AVAILABLE', 'transition: old_status should be AVAILABLE';
    ASSERT h.new_status = 'DAMAGED', 'transition: new_status should be DAMAGED';
    ASSERT h.reason = 'verify', 'transition: reason should be recorded';

    -- 3. P0002 contract: unknown id on transition
    BEGIN
        PERFORM transition_equipment_status(
            p_equipment_id => v_missing,
            p_new_status => 'AVAILABLE',
            p_changed_by => v_staff
        );
        RAISE EXCEPTION 'verify: transition on unknown id should raise P0002';
    EXCEPTION
        WHEN SQLSTATE 'P0002' THEN NULL;  -- expected
    END;

    -- 4. update_equipment_quantity: logs old->new and updates the row
    v := update_equipment_quantity(
        p_equipment_id => v.id,
        p_new_quantity => 6,
        p_changed_by => v_staff
    );
    SELECT * INTO q FROM equipment_quantity_history WHERE equipment_id = v.id;
    ASSERT q.old_quantity = 4, 'quantity: history old_quantity should be 4';
    ASSERT q.new_quantity = 6, 'quantity: history new_quantity should be 6';
    ASSERT v.total_owned_quantity = 6, 'quantity: returned row should carry 6';

    -- 5. P0002 contract: unknown id on quantity update
    BEGIN
        PERFORM update_equipment_quantity(
            p_equipment_id => v_missing,
            p_new_quantity => 1,
            p_changed_by => v_staff
        );
        RAISE EXCEPTION 'verify: quantity update on unknown id should raise P0002';
    EXCEPTION
        WHEN SQLSTATE 'P0002' THEN NULL;  -- expected
    END;

    -- 6. quantity CHECK constraint refuses negatives
    BEGIN
        PERFORM update_equipment_quantity(
            p_equipment_id => v.id,
            p_new_quantity => -1,
            p_changed_by => v_staff
        );
        RAISE EXCEPTION 'verify: negative quantity should violate the CHECK constraint';
    EXCEPTION
        WHEN check_violation THEN NULL;  -- expected
    END;

    RAISE NOTICE 'ALL EQUIPMENT FUNCTION VERIFICATIONS PASSED';
END $$;

ROLLBACK;
