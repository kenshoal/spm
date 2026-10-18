-- Cancel one venue booking request (SCRUM-61). Run after 0041. Safe to re-run.
--
-- A coordinator can cancel a booking while it is pending or approved. A
-- cancelled request keeps who cancelled it and when, and keeps any earlier
-- decision fields. Cancelling an approved request frees its slots at once,
-- because the approval and block checks (0024) only count approved requests.
-- rejected and cancelled are final.
--
-- cancel_venue_booking_request locks the request row, so two cancels, or a
-- cancel racing an approval, cannot both succeed. It does not lock the venues
-- row: cancelling can only free slots, so there is no check to protect.
--
-- Errors: P0002 the request does not exist; 55000 it is not pending or
-- approved; 22023 no cancelling user was given.
--
-- Who may cancel (the event's current Coordinator) is checked by venueService
-- with eventRequestService before this function is called. Browser roles cannot
-- execute it.

ALTER TABLE public.venue_booking_requests
    ADD COLUMN IF NOT EXISTS cancelled_by uuid,
    ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;

-- The decision fields still agree with the status. A cancelled request carries
-- no reason or alternative; it keeps its decider and time only if it had been
-- decided (approved) before it was cancelled.
ALTER TABLE public.venue_booking_requests
    DROP CONSTRAINT IF EXISTS venue_booking_requests_decision_consistent;
ALTER TABLE public.venue_booking_requests
    ADD CONSTRAINT venue_booking_requests_decision_consistent
    CHECK (
        (status = 'pending'
            AND decided_by IS NULL
            AND decided_at IS NULL
            AND decision_reason IS NULL
            AND suggested_alternative IS NULL)
        OR (status = 'approved'
            AND decided_by IS NOT NULL
            AND decided_at IS NOT NULL
            AND decision_reason IS NULL
            AND suggested_alternative IS NULL)
        OR (status = 'rejected'
            AND decided_by IS NOT NULL
            AND decided_at IS NOT NULL
            AND decision_reason IS NOT NULL
            AND btrim(decision_reason) <> '')
        OR (status = 'cancelled'
            AND decision_reason IS NULL
            AND suggested_alternative IS NULL
            AND ((decided_by IS NULL AND decided_at IS NULL)
                 OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)))
    );

-- cancelled_by and cancelled_at are set together, and only when cancelled.
ALTER TABLE public.venue_booking_requests
    DROP CONSTRAINT IF EXISTS venue_booking_requests_cancelled_consistent;
ALTER TABLE public.venue_booking_requests
    ADD CONSTRAINT venue_booking_requests_cancelled_consistent
    CHECK (
        (status = 'cancelled'
            AND cancelled_by IS NOT NULL
            AND cancelled_at IS NOT NULL)
        OR (status <> 'cancelled'
            AND cancelled_by IS NULL
            AND cancelled_at IS NULL)
    );

CREATE OR REPLACE FUNCTION public.cancel_venue_booking_request(
    p_booking_request_id uuid,
    p_cancelled_by uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_request public.venue_booking_requests%ROWTYPE;
BEGIN
    IF p_cancelled_by IS NULL THEN
        RAISE EXCEPTION 'a cancelling user is required' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_request
    FROM public.venue_booking_requests AS r
    WHERE r.id = p_booking_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'booking request not found' USING ERRCODE = 'P0002';
    END IF;

    IF v_request.status NOT IN ('pending', 'approved') THEN
        RAISE EXCEPTION 'booking request cannot be cancelled' USING ERRCODE = '55000';
    END IF;

    UPDATE public.venue_booking_requests AS r
    SET status = 'cancelled',
        cancelled_by = p_cancelled_by,
        cancelled_at = now()
    WHERE r.id = p_booking_request_id
    RETURNING * INTO v_request;
    RETURN to_jsonb(v_request);
END;
$$;

REVOKE ALL ON FUNCTION public.cancel_venue_booking_request(uuid, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_venue_booking_request(uuid, uuid)
    TO service_role;
