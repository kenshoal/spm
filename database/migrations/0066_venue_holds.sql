-- Tentative venue holds (SCRUM-18; Week 7 Customer Change #4). Run once, after 0065.
--
-- The assigned Event Coordinator can hold a venue for their event while it is
-- being finalised (Approved, Planning or Safety Review: after the request is
-- approved and before the event is confirmed). Each hold has an expiry at most
-- 7 days ahead. A hold protects its time only while it is active, unexpired and
-- its event is not Cancelled or Rejected:
--   status = 'active' AND expires_at > now() AND event status NOT IN (Cancelled, Rejected)
-- so at expiry, or when its event is cancelled or rejected, it stops protecting
-- the venue straight away. The event's status is read with the hold, never
-- written to holds by a trigger (Product Owner, 30 October 2026). Holds use the booking time rules (0050)
-- and the venue's setup and turnaround padding (SCRUM-20).
--
-- An active hold blocks overlapping holds, booking approvals and event
-- reschedules (SCRUM-35, 0059), because private.check_booking_candidate (0054)
-- now also reports active holds as hold_conflict with conflicting_hold_ids.
-- A hold never blocks its own event: the guard skips holds whose event owns a
-- booking in p_exclude_ids (approval excludes the request; 0059 excludes the
-- event's bookings), so a converted hold and an event's own unconverted hold
-- never block that event's approval or reschedule.
--
-- Lifecycle: active -> released (by the coordinator, or when its converted
-- request is rejected), converted (its request is approved) or expired (by the
-- sweep). Converting creates a pending booking request through 0056 and links
-- it; the hold keeps protecting the time until Venue Staff decide or the hold
-- expires. A pending request is never approved here.
--
-- Notices: public.sweep_venue_holds marks expired holds and lists the notices
-- that are due ("expiring" 24 hours before expiry, or at once if less remains;
-- "expired" after expiry). venueService sends each with a fixed event_id, which
-- notificationService stores once per recipient, then records it with
-- public.mark_venue_hold_notice, so a retry or catch-up never repeats a notice.
--
-- Locks: every hold writer locks the venue row first, then the hold, then the
-- event, matching approval (0054), booking creation (0056) and reschedules
-- (0059). The sweep locks hold rows only and skips locked ones.
--
-- Errors: P0002 venue, event or hold not found; P0003 caller is not the event's
-- assigned coordinator; P0004 the event cannot hold a venue in its status;
-- 55000 the hold is no longer active, or its conversion is still pending;
-- 22023 invalid times or expiry.

CREATE TABLE public.venue_holds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id uuid NOT NULL REFERENCES public.venues (id),
    event_request_id uuid NOT NULL REFERENCES public.event_requests (id),
    start_date date NOT NULL,
    end_date date NOT NULL,
    start_minute integer NOT NULL,
    end_minute integer NOT NULL,
    expires_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'released', 'converted', 'expired')),
    booking_request_id uuid REFERENCES public.venue_booking_requests (id),
    placed_by uuid NOT NULL,
    placed_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    closed_by uuid,
    expiring_notified_at timestamptz,
    expired_notified_at timestamptz,
    CONSTRAINT venue_holds_dates_valid CHECK (end_date >= start_date),
    CONSTRAINT venue_holds_times_valid CHECK (
        start_minute % 15 = 0 AND end_minute % 15 = 0
        AND start_minute >= 420 AND end_minute <= 1440
        AND end_minute > start_minute
    ),
    CONSTRAINT venue_holds_closed_audit CHECK ((status = 'active') = (closed_at IS NULL))
);

CREATE INDEX venue_holds_venue_active_idx
    ON public.venue_holds (venue_id, start_date, end_date) WHERE status = 'active';
CREATE INDEX venue_holds_event_idx ON public.venue_holds (event_request_id, placed_at);
CREATE INDEX venue_holds_booking_idx
    ON public.venue_holds (booking_request_id) WHERE booking_request_id IS NOT NULL;

ALTER TABLE public.venue_holds ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.venue_holds FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.venue_holds TO service_role;

ALTER TABLE public.venue_booking_refusals
    ADD COLUMN conflicting_hold_ids uuid[] NOT NULL DEFAULT '{}',
    DROP CONSTRAINT venue_booking_refusals_codes_known,
    ADD CONSTRAINT venue_booking_refusals_codes_known
        CHECK (
            cardinality(refusal_codes) > 0
            AND refusal_codes <@ ARRAY[
                'venue_unavailable',
                'outside_operating_slots',
                'active_block',
                'setup_outside_window',
                'turnaround_outside_window',
                'booking_conflict',
                'hold_conflict'
            ]::text[]
        );

-- Unchanged from 0054 except that holds that still protect their time also
-- conflict. p_exclude_ids excludes bookings, holds, and the holds of every
-- event that owns an excluded booking.
CREATE OR REPLACE FUNCTION private.check_booking_candidate(
    p_venue_id uuid,
    p_start_date date,
    p_end_date date,
    p_start_minute integer,
    p_end_minute integer,
    p_exclude_ids uuid[] DEFAULT '{}'
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_setup integer;
    v_turnaround integer;
    v_codes text[] := '{}';
    v_bookings uuid[];
    v_holds uuid[];
    v_exclude uuid[] := COALESCE(p_exclude_ids, '{}');
BEGIN
    IF p_venue_id IS NULL OR p_start_date IS NULL OR p_end_date IS NULL
       OR p_start_minute IS NULL OR p_end_minute IS NULL THEN
        RAISE EXCEPTION 'a candidate needs a venue, dates and times' USING ERRCODE = '22023';
    END IF;
    IF p_end_date < p_start_date
       OR p_start_minute % 15 <> 0 OR p_end_minute % 15 <> 0
       OR p_start_minute < 420 OR p_end_minute > 1440
       OR p_end_minute <= p_start_minute THEN
        RAISE EXCEPTION 'candidate time breaks the booking time rules' USING ERRCODE = '22023';
    END IF;

    SELECT v.setup_minutes, v.turnaround_minutes INTO v_setup, v_turnaround
    FROM public.venues AS v
    WHERE v.id = p_venue_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'venue not found' USING ERRCODE = 'P0002';
    END IF;

    IF p_start_minute - v_setup < 420 THEN
        v_codes := v_codes || 'setup_outside_window'::text;
    END IF;
    IF p_end_minute + v_turnaround > 1440 THEN
        v_codes := v_codes || 'turnaround_outside_window'::text;
    END IF;

    -- Same venue, so both ranges carry the same padding.
    SELECT COALESCE(array_agg(o.id ORDER BY o.start_date, o.start_minute, o.id), '{}')
    INTO v_bookings
    FROM public.venue_booking_requests AS o
    WHERE o.venue_id = p_venue_id
      AND o.status = 'approved'
      AND o.id <> ALL (v_exclude)
      AND o.start_date <= p_end_date
      AND p_start_date <= o.end_date
      AND o.start_minute - v_setup < p_end_minute + v_turnaround
      AND p_start_minute - v_setup < o.end_minute + v_turnaround;
    IF cardinality(v_bookings) > 0 THEN
        v_codes := v_codes || 'booking_conflict'::text;
    END IF;

    SELECT COALESCE(array_agg(h.id ORDER BY h.start_date, h.start_minute, h.id), '{}')
    INTO v_holds
    FROM public.venue_holds AS h
    WHERE h.venue_id = p_venue_id
      AND h.status = 'active'
      AND h.expires_at > now()
      AND h.id <> ALL (v_exclude)
      AND h.event_request_id <> ALL (ARRAY(
          SELECT b.event_request_id FROM public.venue_booking_requests AS b
          WHERE b.id = ANY (v_exclude)
      ))
      AND EXISTS (
          SELECT 1 FROM public.event_requests AS e
          WHERE e.id = h.event_request_id AND e.status NOT IN ('Cancelled', 'Rejected')
      )
      AND h.start_date <= p_end_date
      AND p_start_date <= h.end_date
      AND h.start_minute - v_setup < p_end_minute + v_turnaround
      AND p_start_minute - v_setup < h.end_minute + v_turnaround;
    IF cardinality(v_holds) > 0 THEN
        v_codes := v_codes || 'hold_conflict'::text;
    END IF;

    RETURN jsonb_build_object(
        'refusal_codes', to_jsonb(v_codes),
        'conflicting_booking_ids', to_jsonb(v_bookings),
        'conflicting_hold_ids', to_jsonb(v_holds)
    );
END;
$$;

-- Unchanged from 0054 except that refusals list conflicting holds and a decision
-- on a converted hold's request ends that hold (SCRUM-18).
CREATE OR REPLACE FUNCTION public.decide_venue_booking_request(
    p_booking_request_id uuid,
    p_decision text,
    p_decided_by uuid,
    p_decision_reason text DEFAULT NULL,
    p_suggested_alternative text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_venue_id uuid;
    v_venue public.venues%ROWTYPE;
    v_request public.venue_booking_requests%ROWTYPE;
    v_reason text := NULLIF(btrim(p_decision_reason), '');
    v_alternative text := NULLIF(btrim(p_suggested_alternative), '');
    v_codes text[] := '{}';
    v_blocks uuid[];
    v_guard jsonb;
    v_bookings uuid[];
    v_holds uuid[];
BEGIN
    IF p_decision IS NULL OR p_decision NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'decision must be approved or rejected' USING ERRCODE = '22023';
    END IF;
    IF p_decision = 'rejected' AND v_reason IS NULL THEN
        RAISE EXCEPTION 'a rejection needs a reason' USING ERRCODE = '22023';
    END IF;
    IF p_decision = 'approved' AND (v_reason IS NOT NULL OR v_alternative IS NOT NULL) THEN
        RAISE EXCEPTION 'an approval carries no reason or alternative' USING ERRCODE = '22023';
    END IF;

    SELECT r.venue_id INTO v_venue_id
    FROM public.venue_booking_requests AS r
    WHERE r.id = p_booking_request_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'booking request not found' USING ERRCODE = 'P0002';
    END IF;

    -- Venue first, then the request: the same order as create_venue_block.
    SELECT * INTO v_venue FROM public.venues AS v WHERE v.id = v_venue_id FOR UPDATE;
    SELECT * INTO v_request
    FROM public.venue_booking_requests AS r
    WHERE r.id = p_booking_request_id
    FOR UPDATE;

    IF v_request.status <> 'pending' THEN
        RAISE EXCEPTION 'booking request has already been decided' USING ERRCODE = '55000';
    END IF;

    IF p_decision = 'rejected' THEN
        UPDATE public.venue_booking_requests AS r
        SET status = 'rejected',
            decision_reason = v_reason,
            suggested_alternative = v_alternative,
            decided_by = p_decided_by,
            decided_at = now()
        WHERE r.id = p_booking_request_id
        RETURNING * INTO v_request;
        -- SCRUM-18: a rejected conversion ends its hold. An expired hold is left to
        -- the sweep, which marks it expired and sends its notice.
        UPDATE public.venue_holds AS h
        SET status = 'released', closed_at = now(), closed_by = p_decided_by
        WHERE h.booking_request_id = v_request.id AND h.status = 'active'
          AND h.expires_at > now();
        RETURN jsonb_build_object('outcome', 'rejected', 'booking', to_jsonb(v_request));
    END IF;

    IF v_venue.status <> 'available' THEN
        v_codes := v_codes || 'venue_unavailable'::text;
    END IF;

    -- SCRUM-65: a shared day and overlapping half-open time ranges.
    SELECT COALESCE(array_agg(b.id ORDER BY b.id), '{}') INTO v_blocks
    FROM public.venue_blocks AS b
    WHERE b.venue_id = v_venue_id
      AND b.status = 'active'
      AND b.start_date <= v_request.end_date
      AND v_request.start_date <= b.end_date
      AND b.start_minute < v_request.end_minute
      AND v_request.start_minute < b.end_minute;
    IF cardinality(v_blocks) > 0 THEN
        v_codes := v_codes || 'active_block'::text;
    END IF;

    -- SCRUM-20: setup and turnaround padding, excluding the request itself.
    v_guard := private.check_booking_candidate(
        v_venue_id, v_request.start_date, v_request.end_date,
        v_request.start_minute, v_request.end_minute, ARRAY[v_request.id]
    );
    v_codes := v_codes || ARRAY(SELECT jsonb_array_elements_text(v_guard -> 'refusal_codes'));
    v_bookings := ARRAY(
        SELECT jsonb_array_elements_text(v_guard -> 'conflicting_booking_ids')::uuid
    );
    v_holds := ARRAY(
        SELECT jsonb_array_elements_text(v_guard -> 'conflicting_hold_ids')::uuid
    );

    IF cardinality(v_codes) > 0 THEN
        INSERT INTO public.venue_booking_refusals (
            booking_request_id, refused_by, refusal_codes,
            conflicting_block_ids, conflicting_booking_ids, conflicting_hold_ids
        )
        VALUES (p_booking_request_id, p_decided_by, v_codes, v_blocks, v_bookings, v_holds);
        RETURN jsonb_build_object(
            'outcome', 'refused',
            'refusal_codes', to_jsonb(v_codes),
            'conflicting_block_ids', to_jsonb(v_blocks),
            'conflicting_booking_ids', to_jsonb(v_bookings),
            'conflicting_hold_ids', to_jsonb(v_holds),
            'booking', to_jsonb(v_request)
        );
    END IF;

    UPDATE public.venue_booking_requests AS r
    SET status = 'approved',
        decided_by = p_decided_by,
        decided_at = now()
    WHERE r.id = p_booking_request_id
    RETURNING * INTO v_request;
    -- SCRUM-18: an approved conversion becomes the booking, so its hold ends. An
    -- expired hold is never converted; the sweep marks it expired.
    UPDATE public.venue_holds AS h
    SET status = 'converted', closed_at = now(), closed_by = p_decided_by
    WHERE h.booking_request_id = v_request.id AND h.status = 'active'
      AND h.expires_at > now();
    RETURN jsonb_build_object('outcome', 'approved', 'booking', to_jsonb(v_request));
END;
$$;

CREATE FUNCTION public.place_venue_hold(
    p_venue_id uuid,
    p_event_request_id uuid,
    p_start_date date,
    p_end_date date,
    p_start_minute integer,
    p_end_minute integer,
    p_expires_at timestamptz,
    p_placed_by uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_venue public.venues%ROWTYPE;
    v_event public.event_requests%ROWTYPE;
    v_coordinator varchar;
    v_codes text[] := '{}';
    v_blocks uuid[];
    v_guard jsonb;
    v_hold public.venue_holds%ROWTYPE;
BEGIN
    IF p_venue_id IS NULL OR p_event_request_id IS NULL OR p_placed_by IS NULL
       OR p_start_date IS NULL OR p_end_date IS NULL
       OR p_start_minute IS NULL OR p_end_minute IS NULL OR p_expires_at IS NULL THEN
        RAISE EXCEPTION 'a hold needs a venue, event, dates, times, expiry and coordinator'
            USING ERRCODE = '22023';
    END IF;
    IF p_expires_at <= now() OR p_expires_at > now() + interval '7 days' THEN
        RAISE EXCEPTION 'a hold must expire within the next 7 days' USING ERRCODE = '22023';
    END IF;
    IF p_end_date < p_start_date
       OR p_start_minute % 15 <> 0 OR p_end_minute % 15 <> 0
       OR p_start_minute < 420 OR p_end_minute > 1440
       OR p_end_minute <= p_start_minute THEN
        RAISE EXCEPTION 'hold time breaks the booking time rules' USING ERRCODE = '22023';
    END IF;

    -- Venue first, then the event, as booking creation (0056) does.
    SELECT * INTO v_venue FROM public.venues AS v WHERE v.id = p_venue_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'venue not found' USING ERRCODE = 'P0002';
    END IF;
    SELECT * INTO v_event FROM public.event_requests AS e
    WHERE e.id = p_event_request_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'event request not found' USING ERRCODE = 'P0002';
    END IF;
    SELECT a.coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments AS a
    WHERE a.event_request_id = p_event_request_id ORDER BY a.id DESC LIMIT 1;
    IF v_coordinator IS DISTINCT FROM p_placed_by::text THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    IF v_event.status NOT IN ('Approved', 'Planning', 'Safety Review') THEN
        RAISE EXCEPTION 'the event cannot hold a venue in its current status'
            USING ERRCODE = 'P0004';
    END IF;

    IF v_venue.status <> 'available' THEN
        v_codes := v_codes || 'venue_unavailable'::text;
    END IF;
    -- Blocks are compared without padding, as booking approval does.
    SELECT COALESCE(array_agg(b.id ORDER BY b.id), '{}') INTO v_blocks
    FROM public.venue_blocks AS b
    WHERE b.venue_id = p_venue_id
      AND b.status = 'active'
      AND b.start_date <= p_end_date
      AND p_start_date <= b.end_date
      AND b.start_minute < p_end_minute
      AND p_start_minute < b.end_minute;
    IF cardinality(v_blocks) > 0 THEN
        v_codes := v_codes || 'active_block'::text;
    END IF;
    v_guard := private.check_booking_candidate(
        p_venue_id, p_start_date, p_end_date, p_start_minute, p_end_minute, '{}'
    );
    v_codes := v_codes || ARRAY(SELECT jsonb_array_elements_text(v_guard -> 'refusal_codes'));

    IF cardinality(v_codes) > 0 THEN
        RETURN jsonb_build_object(
            'outcome', 'refused',
            'refusal_codes', to_jsonb(v_codes),
            'conflicting_block_ids', to_jsonb(v_blocks),
            'conflicting_booking_ids', v_guard -> 'conflicting_booking_ids',
            'conflicting_hold_ids', v_guard -> 'conflicting_hold_ids'
        );
    END IF;

    INSERT INTO public.venue_holds (
        venue_id, event_request_id, start_date, end_date, start_minute, end_minute,
        expires_at, placed_by
    )
    VALUES (
        p_venue_id, p_event_request_id, p_start_date, p_end_date, p_start_minute, p_end_minute,
        p_expires_at, p_placed_by
    )
    RETURNING * INTO v_hold;
    RETURN jsonb_build_object('outcome', 'placed', 'hold', to_jsonb(v_hold));
END;
$$;

-- Locks the hold's venue, then the hold, then the event, and checks the caller
-- is the event's current coordinator (the latest assignment, as for SCRUM-38 and
-- SCRUM-19) and that the hold still protects its time.
CREATE FUNCTION private.lock_active_venue_hold(p_hold_id uuid, p_coordinator uuid)
RETURNS public.venue_holds
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_venue_id uuid;
    v_hold public.venue_holds%ROWTYPE;
    v_event_status text;
    v_coordinator varchar;
BEGIN
    SELECT h.venue_id INTO v_venue_id FROM public.venue_holds AS h WHERE h.id = p_hold_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'hold not found' USING ERRCODE = 'P0002';
    END IF;
    PERFORM 1 FROM public.venues AS v WHERE v.id = v_venue_id FOR UPDATE;
    SELECT * INTO v_hold FROM public.venue_holds AS h WHERE h.id = p_hold_id FOR UPDATE;
    SELECT e.status INTO v_event_status
    FROM public.event_requests AS e WHERE e.id = v_hold.event_request_id FOR UPDATE;
    SELECT a.coordinator_id INTO v_coordinator
    FROM public.event_coordinator_assignments AS a
    WHERE a.event_request_id = v_hold.event_request_id ORDER BY a.id DESC LIMIT 1;
    IF p_coordinator IS NULL OR v_coordinator IS DISTINCT FROM p_coordinator::text THEN
        RAISE EXCEPTION 'caller is not the assigned coordinator' USING ERRCODE = 'P0003';
    END IF;
    IF v_hold.status <> 'active' OR v_hold.expires_at <= now()
       OR v_event_status IN ('Cancelled', 'Rejected') THEN
        RAISE EXCEPTION 'the hold is no longer active' USING ERRCODE = '55000';
    END IF;
    RETURN v_hold;
END;
$$;

CREATE FUNCTION public.release_venue_hold(p_hold_id uuid, p_released_by uuid)
RETURNS public.venue_holds
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_hold public.venue_holds%ROWTYPE;
BEGIN
    v_hold := private.lock_active_venue_hold(p_hold_id, p_released_by);
    UPDATE public.venue_holds AS h
    SET status = 'released', closed_at = now(), closed_by = p_released_by
    WHERE h.id = p_hold_id
    RETURNING * INTO v_hold;
    RETURN v_hold;
END;
$$;

-- p_booking carries the new request's id and requested_by (the coordinator);
-- its venue, event, dates and times always come from the hold. The request is
-- created Pending through 0056, which re-checks the coordinator and the event
-- version.
CREATE FUNCTION public.convert_venue_hold(
    p_hold_id uuid,
    p_booking jsonb,
    p_expected_event_updated_at timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_hold public.venue_holds%ROWTYPE;
    v_requested_by uuid;
    v_booking public.venue_booking_requests%ROWTYPE;
BEGIN
    IF pg_catalog.jsonb_typeof(p_booking) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'A booking object is required' USING ERRCODE = '22023';
    END IF;
    BEGIN
        v_requested_by := (p_booking ->> 'requested_by')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'Invalid booking values' USING ERRCODE = '22023';
    END;
    v_hold := private.lock_active_venue_hold(p_hold_id, v_requested_by);
    IF v_hold.booking_request_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.venue_booking_requests AS r
        WHERE r.id = v_hold.booking_request_id AND r.status = 'pending'
    ) THEN
        RAISE EXCEPTION 'the hold already has a pending booking request' USING ERRCODE = '55000';
    END IF;

    v_booking := public.create_event_venue_booking_request(
        p_booking || jsonb_build_object(
            'venue_id', v_hold.venue_id,
            'event_request_id', v_hold.event_request_id,
            'start_date', v_hold.start_date,
            'end_date', v_hold.end_date,
            'start_minute', v_hold.start_minute,
            'end_minute', v_hold.end_minute,
            'status', 'pending'
        ),
        p_expected_event_updated_at
    );
    UPDATE public.venue_holds AS h
    SET booking_request_id = v_booking.id
    WHERE h.id = p_hold_id
    RETURNING * INTO v_hold;
    RETURN jsonb_build_object('hold', to_jsonb(v_hold), 'booking', to_jsonb(v_booking));
END;
$$;

-- Marks holds whose expiry has passed as expired and returns the notices due
-- at p_as_of, with the event's current coordinator as recipient. Skips rows
-- another writer holds; they are picked up on the next run.
CREATE FUNCTION public.sweep_venue_holds(p_as_of timestamptz)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_notices jsonb;
BEGIN
    IF p_as_of IS NULL THEN
        RAISE EXCEPTION 'a sweep time is required' USING ERRCODE = '22023';
    END IF;
    UPDATE public.venue_holds AS h
    SET status = 'expired', closed_at = h.expires_at
    WHERE h.id IN (
        SELECT d.id FROM public.venue_holds AS d
        WHERE d.status = 'active' AND d.expires_at <= p_as_of
        FOR UPDATE SKIP LOCKED
    );

    SELECT COALESCE(jsonb_agg(n ORDER BY n.expires_at, n.hold_id, n.kind), '[]') INTO v_notices
    FROM (
        SELECT h.id AS hold_id, kind.kind, h.venue_id, v.name AS venue_name,
               h.event_request_id, e.event_name, h.start_date, h.end_date,
               h.start_minute, h.end_minute, h.expires_at,
               (SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
                WHERE a.event_request_id = h.event_request_id
                ORDER BY a.id DESC LIMIT 1) AS recipient_id
        FROM public.venue_holds AS h
        JOIN public.venues AS v ON v.id = h.venue_id
        JOIN public.event_requests AS e ON e.id = h.event_request_id
        CROSS JOIN LATERAL (
            SELECT 'expiring'::text AS kind
            WHERE h.status = 'active' AND h.expiring_notified_at IS NULL
              AND h.expires_at > p_as_of AND h.expires_at - interval '24 hours' <= p_as_of
            UNION ALL
            SELECT 'expired'
            WHERE h.status = 'expired' AND h.expired_notified_at IS NULL
        ) AS kind
        WHERE e.status NOT IN ('Cancelled', 'Rejected')
    ) AS n
    WHERE n.recipient_id IS NOT NULL;
    RETURN v_notices;
END;
$$;

-- Records that a notice was delivered, so it is not listed again.
CREATE FUNCTION public.mark_venue_hold_notice(p_hold_id uuid, p_kind text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF p_kind = 'expiring' THEN
        UPDATE public.venue_holds AS h
        SET expiring_notified_at = COALESCE(h.expiring_notified_at, now())
        WHERE h.id = p_hold_id;
    ELSIF p_kind = 'expired' THEN
        UPDATE public.venue_holds AS h
        SET expired_notified_at = COALESCE(h.expired_notified_at, now())
        WHERE h.id = p_hold_id;
    ELSE
        RAISE EXCEPTION 'unknown notice kind' USING ERRCODE = '22023';
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION private.lock_active_venue_hold(uuid, uuid)
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.place_venue_hold(uuid, uuid, date, date, integer, integer, timestamptz, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.place_venue_hold(uuid, uuid, date, date, integer, integer, timestamptz, uuid)
    TO service_role;
REVOKE ALL ON FUNCTION public.release_venue_hold(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.release_venue_hold(uuid, uuid) TO service_role;
REVOKE ALL ON FUNCTION public.convert_venue_hold(uuid, jsonb, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.convert_venue_hold(uuid, jsonb, timestamptz) TO service_role;
REVOKE ALL ON FUNCTION public.sweep_venue_holds(timestamptz) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sweep_venue_holds(timestamptz) TO service_role;
REVOKE ALL ON FUNCTION public.mark_venue_hold_notice(uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mark_venue_hold_notice(uuid, text) TO service_role;
