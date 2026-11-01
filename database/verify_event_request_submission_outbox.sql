-- Run after 0008_event_request_submission_outbox.sql.
-- Every mutation is rolled back, so this leaves no event-request or outbox data behind.

BEGIN;

DO $$
DECLARE
    test_organiser_id uuid;
    draft_request_id uuid;
    direct_request_id uuid;
    recorded_events integer;
BEGIN
    SELECT id INTO test_organiser_id
    FROM auth.users
    ORDER BY created_at
    LIMIT 1;

    IF test_organiser_id IS NULL THEN
        RAISE EXCEPTION 'Verification requires at least one Supabase Auth user';
    END IF;

    -- SCRUM-8 AC6-N1, SCRUM-11 AC8-N1 (negative): a Draft insert records no
    -- submission outbox event.
    INSERT INTO public.event_requests (organiser_id, status, event_name)
    VALUES (test_organiser_id, 'Draft', 'AC9 draft verification')
    RETURNING id INTO draft_request_id;

    SELECT count(*) INTO recorded_events
    FROM public.event_request_outbox
    WHERE event_request_id = draft_request_id;

    IF recorded_events <> 0 THEN
        RAISE EXCEPTION 'A Draft insert must not record a submission event';
    END IF;

    -- SCRUM-11 AC8-H1 (happy): the Draft-to-Submitted write records exactly one
    -- event_request.submitted event.
    UPDATE public.event_requests
    SET status = 'Submitted'
    WHERE id = draft_request_id AND status = 'Draft';

    -- SCRUM-11 AC8-X1 (cross-cutting): a repeated status write records no second
    -- event (UNIQUE (event_request_id, event_type) + ON CONFLICT DO NOTHING).
    -- A retry or repeated write cannot record a second event.
    UPDATE public.event_requests
    SET status = 'Submitted'
    WHERE id = draft_request_id;

    SELECT count(*) INTO recorded_events
    FROM public.event_request_outbox
    WHERE event_request_id = draft_request_id
      AND event_type = 'event_request.submitted';

    IF recorded_events <> 1 THEN
        RAISE EXCEPTION
            'Draft submission recorded % events instead of exactly one',
            recorded_events;
    END IF;

    -- SCRUM-11 AC8-P1, AC2 (partition): a direct submission carrying "Not
    -- required" / "Not known yet" placeholders records exactly one event.
    INSERT INTO public.event_requests (
        organiser_id,
        status,
        event_name,
        purpose,
        description,
        proposed_date_times,
        expected_attendance,
        venue_requirements,
        accessibility_needs,
        equipment_requirements,
        registration_needs
    )
    VALUES (
        test_organiser_id,
        'Submitted',
        'AC9 direct verification',
        'Verify direct submission',
        'Rollback-only database verification',
        ARRAY['2026-10-20T02:00:00Z'::timestamptz],
        20,
        'Not known yet',
        'Not required',
        'Not required',
        'Not known yet'
    )
    RETURNING id INTO direct_request_id;

    SELECT count(*) INTO recorded_events
    FROM public.event_request_outbox
    WHERE event_request_id = direct_request_id
      AND event_type = 'event_request.submitted';

    IF recorded_events <> 1 THEN
        RAISE EXCEPTION
            'Direct submission recorded % events instead of exactly one',
            recorded_events;
    END IF;

    RAISE NOTICE 'ALL EVENT-REQUEST OUTBOX VERIFICATIONS PASSED';
END;
$$;

ROLLBACK;
