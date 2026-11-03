-- Hotfix 2 (H2): a waiting-list offer must end before registration closes. Run once,
-- after 0086.
--
-- SCRUM-24 AC2: a new offer is allowed only when its 72-hour window ends before both
-- registration close and the earliest event start. 0068 checked the start only, so a
-- place freed in the last 72 hours before registration closed was still offered, and the
-- attendee could not use it.
--
-- offer_open_place is used by a withdrawal, by the timer after an expiry and when the
-- capacity is raised, so changing it covers all three. The Coordinator's choice
-- (choose_waitlist_recipient, AC3) is a new offer too and gets the same check; its
-- refusal is P0004 'offer window' and changes nothing. When the window does not fit,
-- the place is released to normal registration, which AC9 and AC11 already describe.
-- Waiting entries still close at the start minus 72 hours only (AC10).
-- 0068 is not edited: both functions are replaced here.

CREATE OR REPLACE FUNCTION private.offer_open_place(
    p_event_request_id uuid,
    p_place_id uuid,
    p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_entry public.event_waitlist_entries;
    v_start timestamptz;
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id;

    SELECT min(d) INTO v_start FROM unnest(v_event.proposed_date_times) AS d;

    SELECT * INTO v_entry
    FROM public.event_waitlist_entries AS e
    WHERE e.event_request_id = p_event_request_id
      AND e.status = 'Waiting'
      -- D7: only a lapsed place is never theirs again; a revoked holder is
      -- eligible for the same place (AC3-H2).
      AND NOT EXISTS (
            SELECT 1 FROM public.event_waitlist_place_offers po
            WHERE po.place_id = p_place_id
              AND po.attendee_id = e.attendee_id
              AND po.outcome = 'Lapsed'
      )
    ORDER BY e.queued_at, e.seq
    LIMIT 1
    FOR UPDATE OF e;

    IF NOT FOUND THEN
        UPDATE public.event_waitlist_places
        SET closed_at = p_now, outcome = 'Released'
        WHERE id = p_place_id AND closed_at IS NULL;
        RETURN;
    END IF;

    IF v_start IS NULL OR NOT (p_now + interval '72 hours' < v_start)
       OR (v_event.registration_closes_at IS NOT NULL
           AND NOT (p_now + interval '72 hours' < v_event.registration_closes_at)) THEN
        UPDATE public.event_waitlist_places
        SET closed_at = p_now, outcome = 'Released'
        WHERE id = p_place_id AND closed_at IS NULL;
        RETURN;
    END IF;

    UPDATE public.event_waitlist_entries
    SET status = 'Offered',
        offered_at = p_now,
        expires_at = p_now + interval '72 hours',
        place_id = p_place_id
    WHERE id = v_entry.id;

    INSERT INTO public.event_waitlist_place_offers (place_id, attendee_id, outcome)
    VALUES (p_place_id, v_entry.attendee_id, 'Offered')
    ON CONFLICT (place_id, attendee_id) DO UPDATE SET outcome = 'Offered';

    INSERT INTO public.waitlist_notification_outbox
        (entry_id, recipient_id, event_type, idempotency_key, payload, occurred_at)
    VALUES (
        v_entry.id,
        v_entry.attendee_id,
        'waitlist_offered',
        'waitlist-offered:' || v_entry.id || ':' || extract(epoch from p_now),
        jsonb_build_object(
            'event_name', v_event.event_name,
            'expires_at', p_now + interval '72 hours'
        ),
        p_now
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.choose_waitlist_recipient(
    p_event_request_id uuid,
    p_entry_id uuid,
    p_coordinator_id text,
    p_now timestamptz
)
RETURNS public.event_waitlist_entries
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_event public.event_requests;
    v_entry public.event_waitlist_entries;
    v_holder public.event_waitlist_entries;
    v_place public.event_waitlist_places;
BEGIN
    SELECT * INTO v_event
    FROM public.event_requests
    WHERE id = p_event_request_id
    FOR UPDATE;

    -- The assigned Coordinator only (D9; latest row, as 0060).
    IF NOT FOUND OR v_event.status <> 'Confirmed' OR p_coordinator_id IS DISTINCT FROM (
        SELECT a.coordinator_id FROM public.event_coordinator_assignments AS a
        WHERE a.event_request_id = p_event_request_id ORDER BY a.id DESC LIMIT 1
    ) THEN
        RAISE EXCEPTION 'event not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT * INTO v_entry
    FROM public.event_waitlist_entries
    WHERE id = p_entry_id AND event_request_id = p_event_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'entry not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_entry.status <> 'Waiting' THEN
        RAISE EXCEPTION 'not waiting' USING ERRCODE = 'P0004';
    END IF;

    SELECT * INTO v_place
    FROM public.event_waitlist_places
    WHERE event_request_id = p_event_request_id AND closed_at IS NULL
    ORDER BY opened_at
    LIMIT 1
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no open place' USING ERRCODE = 'P0004';
    END IF;

    -- SCRUM-24 AC2: a new offer, including the Coordinator's choice, must end its 72 hours
    -- before registration closes and before the earliest start. Checked before the holder
    -- in flight is revoked, so a refusal changes nothing.
    IF (SELECT min(d) FROM unnest(v_event.proposed_date_times) AS d) IS NULL
       OR NOT (p_now + interval '72 hours' < (SELECT min(d) FROM unnest(v_event.proposed_date_times) AS d))
       OR (v_event.registration_closes_at IS NOT NULL
           AND NOT (p_now + interval '72 hours' < v_event.registration_closes_at)) THEN
        RAISE EXCEPTION 'offer window' USING ERRCODE = 'P0004';
    END IF;

    -- D9: revoke the automatic offer in flight for this place. The holder
    -- keeps their position (queued_at unchanged) and is told.
    SELECT * INTO v_holder
    FROM public.event_waitlist_entries
    WHERE place_id = v_place.id AND status = 'Offered'
    FOR UPDATE;

    IF FOUND THEN
        UPDATE public.event_waitlist_place_offers
        SET outcome = 'Revoked'
        WHERE place_id = v_place.id AND attendee_id = v_holder.attendee_id;

        UPDATE public.event_waitlist_entries
        SET status = 'Waiting',
            offered_at = NULL,
            expires_at = NULL,
            warned_at = NULL,
            place_id = NULL
        WHERE id = v_holder.id;

        INSERT INTO public.waitlist_notification_outbox
            (entry_id, recipient_id, event_type, idempotency_key, payload, occurred_at)
        VALUES (
            v_holder.id,
            v_holder.attendee_id,
            'waitlist_offer_revoked',
            'waitlist-revoked:' || v_holder.id || ':'
                || extract(epoch from v_holder.offered_at),
            jsonb_build_object('event_name', v_event.event_name),
            p_now
        );
    END IF;

    UPDATE public.event_waitlist_entries
    SET status = 'Offered',
        offered_at = p_now,
        expires_at = p_now + interval '72 hours',
        warned_at = NULL,
        place_id = v_place.id
    WHERE id = v_entry.id
    RETURNING * INTO v_entry;

    INSERT INTO public.event_waitlist_place_offers (place_id, attendee_id, outcome)
    VALUES (v_place.id, v_entry.attendee_id, 'Offered')
    ON CONFLICT (place_id, attendee_id) DO UPDATE SET outcome = 'Offered';

    INSERT INTO public.waitlist_notification_outbox
        (entry_id, recipient_id, event_type, idempotency_key, payload, occurred_at)
    VALUES (
        v_entry.id,
        v_entry.attendee_id,
        'waitlist_offered',
        'waitlist-offered:' || v_entry.id || ':' || extract(epoch from p_now),
        jsonb_build_object(
            'event_name', v_event.event_name,
            'expires_at', p_now + interval '72 hours'
        ),
        p_now
    );

    RETURN v_entry;
END;
$$;

REVOKE EXECUTE ON FUNCTION private.offer_open_place(uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.choose_waitlist_recipient(uuid, uuid, text, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.choose_waitlist_recipient(uuid, uuid, text, timestamptz)
    TO service_role;
