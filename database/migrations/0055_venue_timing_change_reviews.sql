-- Venue timing-change reviews (SCRUM-20 AC6). Run once, after 0054, and only once
-- the readers that accept 'venue_timing_change' (PR #85) are deployed.
--
-- public.update_venue_timing changes a venue's setup and/or turnaround in one
-- transaction: it locks the venue row, updates the times, records the change in
-- venue_timing_changes and flags the bookings the change affects in
-- arrangement_reviews (trigger_type 'venue_timing_change', trigger_id = the
-- change's id). 0037's trigger queues the existing arrangement_needs_review
-- notice for each flag, and 0038 delivers it to the event's coordinator and
-- Venue Staff with no change_request_id. If any step fails, nothing is saved.
--
-- Affected bookings (agreed with Heng Rui, 21 October 2026):
--   * approved bookings at the venue whose end_date is on or after today in
--     Singapore, taken once per transaction; ended, pending, rejected and
--     cancelled bookings are not considered;
--   * both bookings of every pair that shares a day and whose padded times
--     overlap under the new setup/turnaround but did not under the old;
--   * any booking whose padded range leaves 07:00-24:00 under the new values but
--     did not under the old.
-- Already-broken pairs or bookings are not flagged again. No booking, approval
-- or event status changes.
--
-- A null argument keeps that time. Unchanged values write nothing, so a retry
-- after commit writes nothing; flags also use ON CONFLICT DO NOTHING.
-- venue_booking_requests.event_request_id has no foreign key, but
-- arrangement_reviews.event_request_id does: an affected booking whose event
-- does not exist cannot carry a review, so it is returned in
-- unlinked_booking_ids instead of failing the change.
--
-- Locks: the venue row FOR UPDATE (the same lock as approval, block creation and
-- the 0054 guard's callers), then event rows only through the FK KEY SHARE taken
-- by the review and outbox inserts, so events are reached last (0039 protocol).
--
-- Errors: P0002 the venue does not exist; 23514 a time breaks
-- venues_setup_minutes_valid / venues_turnaround_minutes_valid.
-- Returns { venue, timing_change_id, flagged_booking_ids, unlinked_booking_ids };
-- timing_change_id is null when nothing changed.

CREATE TABLE public.venue_timing_changes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id uuid NOT NULL REFERENCES public.venues (id),
    old_setup_minutes integer NOT NULL,
    old_turnaround_minutes integer NOT NULL,
    new_setup_minutes integer NOT NULL,
    new_turnaround_minutes integer NOT NULL,
    changed_by uuid NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT venue_timing_changes_changed
        CHECK ((old_setup_minutes, old_turnaround_minutes)
               IS DISTINCT FROM (new_setup_minutes, new_turnaround_minutes))
);

CREATE INDEX venue_timing_changes_venue_idx
    ON public.venue_timing_changes (venue_id, changed_at);

ALTER TABLE public.venue_timing_changes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.venue_timing_changes
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.venue_timing_changes TO service_role;

ALTER TABLE public.arrangement_reviews
    DROP CONSTRAINT arrangement_reviews_trigger_type_check,
    ADD CONSTRAINT arrangement_reviews_trigger_type_check
        CHECK (trigger_type IN (
            'event_change', 'equipment_unavailable', 'safety_recheck', 'venue_timing_change'
        ));

CREATE FUNCTION public.update_venue_timing(
    p_venue_id uuid,
    p_setup_minutes integer,
    p_turnaround_minutes integer,
    p_changed_by uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_venue public.venues%ROWTYPE;
    v_old_setup integer;
    v_old_turnaround integer;
    v_new_setup integer;
    v_new_turnaround integer;
    v_today date := (pg_catalog.transaction_timestamp() AT TIME ZONE 'Asia/Singapore')::date;
    v_change_id uuid;
    v_fields text[] := '{}';
    v_affected jsonb;
    v_flagged uuid[];
    v_unlinked uuid[];
BEGIN
    IF p_changed_by IS NULL THEN
        RAISE EXCEPTION 'a changing user is required' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_venue FROM public.venues AS v WHERE v.id = p_venue_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'venue not found' USING ERRCODE = 'P0002';
    END IF;

    v_old_setup := v_venue.setup_minutes;
    v_old_turnaround := v_venue.turnaround_minutes;
    v_new_setup := COALESCE(p_setup_minutes, v_old_setup);
    v_new_turnaround := COALESCE(p_turnaround_minutes, v_old_turnaround);

    IF (v_new_setup, v_new_turnaround) = (v_old_setup, v_old_turnaround) THEN
        RETURN jsonb_build_object(
            'venue', to_jsonb(v_venue),
            'timing_change_id', NULL,
            'flagged_booking_ids', '[]'::jsonb,
            'unlinked_booking_ids', '[]'::jsonb
        );
    END IF;
    IF v_new_setup <> v_old_setup THEN
        v_fields := v_fields || 'setup_minutes'::text;
    END IF;
    IF v_new_turnaround <> v_old_turnaround THEN
        v_fields := v_fields || 'turnaround_minutes'::text;
    END IF;

    UPDATE public.venues AS v
    SET setup_minutes = v_new_setup,
        turnaround_minutes = v_new_turnaround,
        updated_at = now()
    WHERE v.id = p_venue_id
    RETURNING * INTO v_venue;

    INSERT INTO public.venue_timing_changes (
        venue_id, old_setup_minutes, old_turnaround_minutes,
        new_setup_minutes, new_turnaround_minutes, changed_by
    )
    VALUES (p_venue_id, v_old_setup, v_old_turnaround, v_new_setup, v_new_turnaround, p_changed_by)
    RETURNING id INTO v_change_id;

    -- Same venue, so every booking carries the same padding.
    WITH current_bookings AS (
        SELECT b.id, b.event_request_id, b.start_date, b.end_date, b.start_minute, b.end_minute
        FROM public.venue_booking_requests AS b
        WHERE b.venue_id = p_venue_id
          AND b.status = 'approved'
          AND b.end_date >= v_today
    ),
    new_pairs AS (
        SELECT a.id AS a_id, o.id AS b_id
        FROM current_bookings AS a
        JOIN current_bookings AS o
          ON a.id < o.id
         AND a.start_date <= o.end_date AND o.start_date <= a.end_date
        WHERE a.start_minute - v_new_setup < o.end_minute + v_new_turnaround
          AND o.start_minute - v_new_setup < a.end_minute + v_new_turnaround
          AND NOT (a.start_minute - v_old_setup < o.end_minute + v_old_turnaround
                   AND o.start_minute - v_old_setup < a.end_minute + v_old_turnaround)
    ),
    clashing AS (
        SELECT a_id AS id FROM new_pairs
        UNION
        SELECT b_id FROM new_pairs
    ),
    outside_window AS (
        SELECT c.id
        FROM current_bookings AS c
        WHERE (c.start_minute - v_new_setup < 420 OR c.end_minute + v_new_turnaround > 1440)
          AND NOT (c.start_minute - v_old_setup < 420 OR c.end_minute + v_old_turnaround > 1440)
    )
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
               'booking_id', c.id,
               'event_request_id', c.event_request_id,
               'clashes', c.id IN (SELECT id FROM clashing),
               'outside', c.id IN (SELECT id FROM outside_window))), '[]')
    INTO v_affected
    FROM current_bookings AS c
    WHERE c.id IN (SELECT id FROM clashing) OR c.id IN (SELECT id FROM outside_window);

    WITH affected AS (
        SELECT * FROM jsonb_to_recordset(v_affected)
            AS a(booking_id uuid, event_request_id uuid, clashes boolean, outside boolean)
    ),
    flagged AS (
        INSERT INTO public.arrangement_reviews
            (event_request_id, arrangement, arrangement_id, trigger_id,
             trigger_type, changed_fields, reason)
        SELECT a.event_request_id, 'venue_booking', a.booking_id, v_change_id,
               'venue_timing_change', v_fields,
               pg_catalog.format(
                   'Venue setup / turnaround changed from %s / %s to %s / %s minutes; this booking now %s.',
                   v_old_setup, v_old_turnaround, v_new_setup, v_new_turnaround,
                   CASE
                       WHEN a.clashes AND a.outside
                           THEN 'clashes with another approved booking and its padding falls outside 07:00-24:00'
                       WHEN a.clashes THEN 'clashes with another approved booking'
                       ELSE 'has padding that falls outside 07:00-24:00'
                   END)
        FROM affected AS a
        JOIN public.event_requests AS e ON e.id = a.event_request_id
        ON CONFLICT ON CONSTRAINT arrangement_reviews_trigger_target_unique DO NOTHING
        RETURNING arrangement_id
    )
    SELECT COALESCE(array_agg(arrangement_id ORDER BY arrangement_id), '{}') INTO v_flagged
    FROM flagged;

    SELECT COALESCE(array_agg(a.booking_id ORDER BY a.booking_id), '{}') INTO v_unlinked
    FROM jsonb_to_recordset(v_affected) AS a(booking_id uuid, event_request_id uuid)
    WHERE NOT EXISTS (SELECT 1 FROM public.event_requests AS e WHERE e.id = a.event_request_id);

    RETURN jsonb_build_object(
        'venue', to_jsonb(v_venue),
        'timing_change_id', v_change_id,
        'flagged_booking_ids', to_jsonb(v_flagged),
        'unlinked_booking_ids', to_jsonb(v_unlinked)
    );
END;
$$;

REVOKE ALL ON FUNCTION public.update_venue_timing(uuid, integer, integer, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.update_venue_timing(uuid, integer, integer, uuid)
    TO service_role;
