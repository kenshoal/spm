-- Run after 0016_venues.sql and 0026_venue_setup_turnaround.sql.
-- Case IDs match docs/testcases/scrum_59_testcases.md (AC4-DB1).
-- Every change is rolled back, so this leaves no venue data behind. Before
-- 0026 is applied it stops at the first statement that needs the columns,
-- which is the intended Red result.

BEGIN;

CREATE TEMP TABLE verify_ctx ON COMMIT DROP AS
SELECT gen_random_uuid() AS venue_id;

INSERT INTO public.venues (
    id, name, location, max_capacity, facilities, accessibility_features,
    supported_layouts, operating_slots
)
SELECT venue_id, 'Verify venue', 'Verify', 50, '{}', '{}', '{}', '{AM}'
FROM verify_ctx;

DO $$
DECLARE
    v_id uuid := (SELECT venue_id FROM verify_ctx);
    v_setup integer;
    v_turnaround integer;
    v_bad integer;
BEGIN
    -- AC4: a venue inserted without the times starts at 0 / 0.
    SELECT setup_minutes, turnaround_minutes INTO v_setup, v_turnaround
    FROM public.venues WHERE id = v_id;
    IF v_setup <> 0 OR v_turnaround <> 0 THEN
        RAISE EXCEPTION 'AC4-DB1: expected 0 / 0, got % / %', v_setup, v_turnaround;
    END IF;

    -- AC1: valid values, including both limits, are stored.
    UPDATE public.venues SET setup_minutes = 30, turnaround_minutes = 45 WHERE id = v_id;
    UPDATE public.venues SET setup_minutes = 0, turnaround_minutes = 1020 WHERE id = v_id;

    -- AC1: off-step, negative and over-limit values are refused by the checks.
    FOREACH v_bad IN ARRAY ARRAY[20, -15, 1035] LOOP
        BEGIN
            UPDATE public.venues SET setup_minutes = v_bad WHERE id = v_id;
            RAISE EXCEPTION 'AC4-DB1: setup_minutes % was accepted', v_bad;
        EXCEPTION WHEN check_violation THEN NULL;
        END;
        BEGIN
            UPDATE public.venues SET turnaround_minutes = v_bad WHERE id = v_id;
            RAISE EXCEPTION 'AC4-DB1: turnaround_minutes % was accepted', v_bad;
        EXCEPTION WHEN check_violation THEN NULL;
        END;
    END LOOP;

    -- The refused updates left the last valid values in place.
    SELECT setup_minutes, turnaround_minutes INTO v_setup, v_turnaround
    FROM public.venues WHERE id = v_id;
    IF v_setup <> 0 OR v_turnaround <> 1020 THEN
        RAISE EXCEPTION 'AC4-DB1: refused updates changed the row (% / %)',
            v_setup, v_turnaround;
    END IF;

    RAISE NOTICE 'SCRUM-59 verify: all venue setup and turnaround cases passed';
END;
$$;

ROLLBACK;
